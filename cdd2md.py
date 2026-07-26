import re
from bs4 import BeautifulSoup, NavigableString
import requests


def url_to_markdown(url):
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


def html_to_markdown(html_content):
    def filter(tag):
        if tag.name == 'style' or tag.name == 'del':
            return True
        if tag.has_attr('class') and\
            (tag['class'] == ['cut-version-block'] or tag['class'] == ['note'] or tag['class'] == ['delta-block-wrap-header', 'delta-block-wrap-bg']\
                or tag['class'] == ['delta-block-wrap-footer', 'delta-block-wrap-bg'] or tag['class'] == ['cut-version-inline']):
            return True
        return False

    soup = BeautifulSoup(html_content, "html5lib")
    body = soup.find('div', class_='devsite-article-body clearfix')
    for e in body(filter):
        e.decompose()

    return parse_element(body)


def parse_element(element):
    markdown_text = ""

    for child in element.children:
        if isinstance(child, NavigableString):
            markdown_text += str(child)
            continue

        tag_name = child.name

        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_name[1])
#            print(f"\n\n{'#' * level} {parse_element(child).strip()}\n\n")
            markdown_text += f"\n\n{'#' * level} {parse_element(child).strip()}\n\n"

        elif tag_name in ["p", "div"]:
#            print(f"\n\n{parse_element(child).strip()}\n\n")
            markdown_text += f"\n\n{parse_element(child).strip()}\n\n"

        elif tag_name in ["strong", "b"]:
#            print(f"**{parse_element(child)}**")
            markdown_text += f"**{parse_element(child)}**"

        elif tag_name in ["em", "i"]:
#            print(f"*{parse_element(child)}*")
            markdown_text += f"*{parse_element(child)}*"

        elif tag_name == "a":
#            href = child.get("href", "")
#            print(f"{parse_element(child)}")
#            markdown_text += f"[{parse_element(child)}]({href})"
            text = parse_element(child)
            markdown_text += text

        elif tag_name == "br":
#            print()
            markdown_text += "  \n"

        elif tag_name in ["ul", "ol"]:
#            print(f"\n\n{parse_element(child).strip()}\n\n")
            markdown_text += f"\n\n{parse_element(child).strip()}\n\n"

        elif tag_name == "li":
            parent_name = child.parent.name if child.parent else "ul"
            if parent_name == "ol":
#                print(f"1. {parse_element(child).strip()}\n")
                markdown_text += f"1. {parse_element(child).strip()}\n"
            else:
#                print(f"* {parse_element(child).strip()}\n")
                markdown_text += f"* {parse_element(child).strip()}\n"

        else:
#            print(parse_element(child))
            markdown_text += parse_element(child)

    return clean_extra_newlines(markdown_text)


def clean_extra_newlines(text):
    # 3つ以上連続する改行を2つにまとめる
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --- 動作確認 ---
if __name__ == "__main__":
    # 変換したいURLを指定してください
    target_url = "https://source.android.com/docs/compatibility/15/android-15-cdd?hl=en"

    print(f"{target_url} からの変換を開始します...\n")
    markdown_result = url_to_markdown(target_url)

    print("--- 変換結果 ---")
    with open('hoge.md', mode='w') as f:
        print(markdown_result, file=f)
