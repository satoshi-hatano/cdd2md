#!/usr/bin/python3

import re
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
def parse_element(element, depth=0):
    def is_requirement(text:str)->bool:
        req_word = ['MUST', 'REQUIRED', 'SHALL', 'SHOULD', 'RECOMMENDED', 'MAY', 'OPTIONAL']
        for w in req_word:
            if w in text:
                return True
        return False

    global CONDITION
    markdown_text = ""

    for child in element.children:
        if isinstance(child, NavigableString):
            # 空白だけの行はスキップする
            if (s := str(child).strip()):
                markdown_text += str(child)
            continue

        tag_name = child.name

        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_name[1])
            markdown_text += f"{'#' * level} {parse_element(child).strip()}\n\n"
            CONDITION = ''

        elif tag_name in ["p", "div"]:
            text = parse_element(child).strip()
            if tag_name == 'p':
                text = text.replace('\n', ' ')
            if tag_name == 'p' and element.name != 'li' and text.endswith(':'):
                # <li>'のサブ要素でない<p>要素で末尾が':'となっているものは条件とみなす
                CONDITION = text
            elif text.strip():
                markdown_text += f"{text}\n\n"

        elif tag_name == "a":
            markdown_text += parse_element(child)

        elif tag_name == "br":
            # <br>タグは後で一括して'\n'に置き換える
            markdown_text += "<br>"

        elif tag_name == 'code':
            markdown_text += parse_element(child)

        elif tag_name in ["ul", "ol"]:
            if element.name == 'li':
                markdown_text += '\n'
                text = f"{parse_element(child, depth + 1)}"
            else:
                text = f"{parse_element(child, depth + 1)}\n\n"
            markdown_text += text

        elif tag_name == "li":
            parent_name = child.parent.name if child.parent else "ul"
            # ネストレベルに応じたインデント（深さ1以上なら半角スペース4つずつ追加）
            indent = "    " * max(0, depth - 1)
            # リスト記号の設定
            prefix = "1. " if parent_name == "ol" else "* "
            if child.string:
                # 子要素がない
                content = child.string.replace('\n', ' ')
            else:
                # 子要素の解析結果を取得
                content = parse_element(child, depth).strip()
                if not re.search('\\n +\\*', content):
                    # 入れ子の<li>がない
                    content = content.replace('\n', ' ')
            if (depth - 1) == 0 and CONDITION:
                # 最上位の<li>で条件がある場合
                if is_requirement(content) or is_requirement(CONDITION):
                    # <li>が要件なら間に条件を挟む
                    if (n := content.find(']') + 1) > 0:
                        # 要件IDがある場合は、要件IDと本文の間に挿入する
                        s1 = content[:n]
                        s2 = content[n:]
                        content = f'{s1} ({CONDITION}){s2}'
                    else:
                        content = f'({CONDITION}){content}'
                else:
                    # 要件でない場合は、条件はそのまま出力する
                    markdown_text += f"{CONDITION}\n\n"
                    CONDITION = ''

            # 1行として出力
            markdown_text += f"{indent}{prefix}{content}\n"
            if depth - 1 == 0:
                markdown_text += '\n'

        elif tag_name == 'table':
            text = table_to_markdown(child) + '\n'
            markdown_text += text

        else:
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


# --- 動作確認 ---
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
    print(f"{args.uri} からの変換を開始します...\n")

    title, markdown = convert_to_markdown(args.uri)

    print("--- 変換結果 ---")
    if not (filename := args.out_file):
        now = datetime.now()
        filename = title + '_{:02d}{:02d}{:02d}'.format(now.year-2000, now.month, now.day) + '.md'
    with open(filename, mode='w') as f:
        print(markdown, file=f)
