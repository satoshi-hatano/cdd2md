#!/usr/bin/python3

import re, sys
from bs4 import BeautifulSoup, NavigableString
import requests
import argparse
from datetime import datetime

def convert_to_markdown(uri:str)->str|str:
    if uri.startswith('http://') or uri.startswith('https://'):
        return url_to_markdown(uri)
    else:
        return file_to_markdown(uri)


def url_to_markdown(url)->str|str:
    try:
        # 1. URLからHTMLを取得（ユーザーエージェントを設定して拒否されにくくする）
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)

        # ステータスコードが200（成功）かチェック
        response.raise_for_status()

        # 文字化け対策（レスポンスから適切なエンコーディングを設定）
        response.encoding = response.apparent_encoding

        # 2. HTMLをMarkdownに変換
        return html_to_markdown(response.text)

    except requests.exceptions.RequestException as e:
        return f"エラー: HTMLの取得に失敗しました。({e})"


def file_to_markdown(path:str)->str|str:
    with open(path, 'r', encoding='UTF-8') as file:
        contents = file.read()
        return html_to_markdown(contents)


def html_to_markdown(html_content)->str|str:
    def filter(tag):
        if tag.name == 'style' or tag.name == 'del':
            return True
        if tag.has_attr('class') and\
            (tag['class'] == ['cut-version-block'] or tag['class'] == ['note'] or tag['class'] == ['delta-block-wrap-header', 'delta-block-wrap-bg']\
                or tag['class'] == ['delta-block-wrap-footer', 'delta-block-wrap-bg'] or tag['class'] == ['cut-version-inline']):
            return True
        return False

    soup = BeautifulSoup(html_content, "html5lib")
    if (h1 := soup.find(lambda t: t.name == 'h1' and t.get('class') == ['devsite-page-title'])):
        title = h1.contents[0].lstrip().rstrip().replace(' ', '_')
    else:
        title = 'output'
    body = soup.find('div', class_='devsite-article-body clearfix')
    for e in body(filter):
        e.decompose()
    markdown = parse_element(body).replace('<br>', '\n')
    return title, markdown


CONDITION = ''
SECTION_NO = ''
def parse_element(element, depth=0):
    # 文が要件(Requirement)か判定する
    def is_requirement(text:str)->bool:
        req_word = ['MUST', 'REQUIRED', 'SHALL', 'SHOULD', 'RECOMMENDED', 'MAY', 'OPTIONAL']
        for w in req_word:
            if w in text:
                return True
        return False
    # 文が条件(Condition)か判定する
    def is_condition(text:str)->bool:
        if text.endswith(':') or re.match(r'^If.+they$', text):
            return True
        return False

    global CONDITION, SECTION_NO
    markdown_text = ""

    for child in element.children:
        if isinstance(child, NavigableString):
            # 空白だけの行はスキップする
            if (s := str(child).strip()):
                markdown_text += str(child)
            continue

        match (tag_name := child.name):
            case "h1" | "h2" | "h3" | "h4" | "h5" | "h6":
                level = int(tag_name[1])
                section = parse_element(child).strip()
                markdown_text += f"{'#' * level} {section}\n"
                SECTION_NO = section[:section.index(' ')]
                CONDITION = ''
    
            case "p" | "div":
                text = parse_element(child).strip()
                if tag_name == 'p':
                    text = text.replace('\n', ' ')
                if tag_name == 'p' and element.name != 'li' and is_condition(text):
                    # <li>'のサブ要素でない<p>要素で末尾が':'となっているものは条件とみなす
                    if not text.endswith(':'):
                        # 末尾が':'になっていない場合は付加する
                        text += ':'
                    CONDITION = text
                elif text.strip():
                    markdown_text += f"{text}\n\n"

            case "a":
                markdown_text += parse_element(child)

            case "br":
                # <br>タグは後で一括して'\n'に置き換える
                markdown_text += "<br>"

            case 'code':
                markdown_text += parse_element(child)

            case "ul" | "ol":
                if element.name == 'li':
                    text = f"{parse_element(child, depth + 1)}\n"
                else:
                    text = f"{parse_element(child, depth + 1)}\n\n"
                if depth == 0:
                    # 行が分割されているli要素を1行にまとめる
                    t = ''
                    for l in text.splitlines():
                        if (s := l.strip()).startswith('* ') or s.startswith('1. '):
                            t += (l + '\n')
                        elif s:
                            t = t[:-1] + f' {s}\n'
                    text = t
                    # 要件の処理
                    need_condition = False
                    lines = text.splitlines()
                    for l in lines:
                        if is_requirement(l):
                            need_condition = True
                            break

                    if need_condition and CONDITION:
                        t = ''
                        # 要件文に条件を挿入する
                        for l in lines:
                            if not is_requirement(l):
                                t += (l + '\n')
                                continue
                            elif (o := l.find('[') + 1) > 1 and (c := l.find(']')) > o:
                                # 要件IDがある場合は、要件IDと本文の間に挿入する
                                # CDDの要件IDはユニークでないため、元のIDにセクションNo.を付加してユニークになるようにする
                                req_id = f'{SECTION_NO}_{l[o:c]}'
                                t += f'[{req_id}] ({CONDITION}){l[c+1:]}\n'
                            else:
                                for m in ['* ', '1. ']:
                                    if (n := l.find(m)) != -1:
                                        n += len(m)
                                        t += f'{l[:n]}({CONDITION}) {l[n:]}\n'
                                        break
                        text = t
                    elif CONDITION:
                        # 要件がない場合は、条件はそのまま出力する。
                        text = f'{CONDITION}\n\n{text}'
                        CONDITION = ''
                    text += '\n'
                markdown_text += text

            case "li":
                parent_name = child.parent.name if child.parent else "ul"
                # ネストレベルに応じたインデント（深さ1以上なら半角スペース4つずつ追加）
                indent = "    " * max(0, depth - 1)
                # リスト記号の設定
                prefix = "1. " if parent_name == "ol" else "* "
                if child.string:
                    content = child.string
                else:
                    content = parse_element(child, depth).strip()
                # 1行として出力
                markdown_text += f"{indent}{prefix}{content}\n"

            case 'table':
                text = table_to_markdown(child) + '\n\n'
                markdown_text += text

            case _:
                markdown_text += parse_element(child)

    return clean_extra_newlines(markdown_text)


def clean_extra_newlines(text):
    # 3つ以上連続する改行を2つにまとめる
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 先頭の「改行のみ」を削除（インデント用の半角スペースは保持）
    text = re.sub(r"^\n+", "", text)

    # 末尾の無駄な空白や改行を削除
    return text.rstrip()


def table_to_markdown(table) -> str:
    """
    Convert BeautifulSoup Table tag object to Markdown format

    Args:
        table: BeautifulSoup Table tag object
    Returns:
        str: Table string in Markdown format
    """
    if not table:
        return "No table found"

    markdown_lines = []

    ## Process headers
    headers = []
    for th in table.find_all('th'):
        ## Replace <br> and <br/> with newline
        header_text = str(th)
        header_text = header_text.replace('<br>', '\n').replace('<br/>', '\n')
        header_soup = BeautifulSoup(header_text, 'html.parser')
        header = re.sub('\\s', ' ', header_soup.get_text()).strip()
        headers.append(header)

    if headers:
        markdown_lines.append('| ' + ' | '.join(headers) + ' |')
        markdown_lines.append('| ' + ' | '.join(['---' for _ in headers]) + ' |')

    ## Process data rows
    for row in table.find_all('tr'):
        cols = []
        for td in row.find_all('td'):
            ## Replace <br> and <br/> with newline
            cell_text = str(td)
            cell_text = cell_text.replace('<br>', '\n').replace('<br/>', '\n')
            cell_soup = BeautifulSoup(cell_text, 'html.parser')
            # col = re.sub('\\s', ' ', cell_soup.get_text()).strip()
            col = cell_soup.get_text().strip()
            ## Replace any remaining newlines with actual line breaks
            col = col.replace('\n', '<br>')
            cols.append(col)
        if cols:  ## Ignore empty rows
            markdown_lines.append('| ' + ' | '.join(cols) + ' |')

    return '\n'.join(markdown_lines)


# main
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='''Android CDDをMarkdown形式に変換する。

パラメータが'http:'または'https:'で始まる場合は、CDDのURLとみなして直接変換する。
そうでない場合は、ローカル保存されたCDDのHTMLファイルとして処理する。

出力されるMarkdownファイルのファイル名は、-oオプションで指定されたものになる。-oオプション省略時は
　　HTMLのタイトル_処理日付.md
となる。''')
    parser.add_argument('-o', dest='out_file', type=str, default='', help='出力するファイル名を指定する。省略時はHTMLのタイトルをファイル名とする')
    parser.add_argument('uri', type=str, nargs='?', default='https://source.android.com/docs/compatibility/15/android-15-cdd?hl=en', help='Android CDDのURLまたはローカルファイルパスを指定する')
    args = parser.parse_args()
    print(f"{args.uri} からの変換を開始\n", file=sys.stderr)

    title, markdown = convert_to_markdown(args.uri)

    if not (filename := args.out_file):
        now = datetime.now()
        filename = title + '_{:02d}{:02d}{:02d}'.format(now.year-2000, now.month, now.day) + '.md'
    with open(filename, mode='w') as f:
        print(markdown, file=f)
    print(f"変換終了：{filename}", file=sys.stderr)
