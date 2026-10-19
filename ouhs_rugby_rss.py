import os
import re
import time
import hashlib
import requests
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin


SOURCE_URL = "https://ouhs-athletics.jp/rugby/clubnews/"
RSS_FILE = "ouhs_rugby.xml"

FEED_TITLE = "大阪体育大学ラグビー部 クラブニュース"
FEED_DESCRIPTION = "大阪体育大学ラグビー部 クラブニュース更新RSS"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}


def clean_text(text):
    return " ".join(text.split()).strip()


def fetch_page():
    last_error = None

    for attempt in range(1, 4):
        try:
            print(f"取得試行 {attempt}/3: {SOURCE_URL}")

            response = requests.get(
                SOURCE_URL,
                headers=HEADERS,
                timeout=30
            )

            print(
                f"HTTP: {response.status_code} / "
                f"取得バイト数: {len(response.content)} / "
                f"最終URL: {response.url}"
            )

            response.raise_for_status()

            response.encoding = (
                response.apparent_encoding
                or response.encoding
                or "utf-8"
            )

            return response.text

        except Exception as e:
            last_error = e
            print(f"取得失敗: {e}")

            if attempt < 3:
                print("10秒待って再試行します。")
                time.sleep(10)

    raise RuntimeError(
        f"ページを取得できませんでした: {last_error}"
    )


def parse_articles(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    articles = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()

        if not href:
            continue

        link = urljoin(
            SOURCE_URL,
            href
        )

        url_match = re.fullmatch(
            r"https://ouhs-athletics\.jp/"
            r"rugby/clubnews/"
            r"(20\d{2})-(\d{2})-(\d{2})-\d+/?",
            link
        )

        if not url_match:
            continue

        year = int(url_match.group(1))
        month = int(url_match.group(2))
        day = int(url_match.group(3))

        published = datetime(
            year,
            month,
            day,
            12,
            0,
            0,
            tzinfo=JST
        )

        full_text = clean_text(
            anchor.get_text(
                " ",
                strip=True
            )
        )

        if not full_text:
            continue

        # リンクテキスト先頭の日付
        # 例: 2026.04.28 タイトル
        title = re.sub(
            r"^20\d{2}\.\d{2}\.\d{2}\s*",
            "",
            full_text
        ).strip()

        if not title:
            continue

        if link not in articles:
            guid = hashlib.sha256(
                link.encode("utf-8")
            ).hexdigest()

            articles[link] = {
                "title": title,
                "link": link,
                "guid": guid,
                "published": published,
                "description": title,
            }

    return list(
        articles.values()
    )


def load_existing_items():
    items = {}

    if not os.path.exists(RSS_FILE):
        return items

    try:
        tree = ET.parse(RSS_FILE)
        root = tree.getroot()

        for item in root.findall(
            "./channel/item"
        ):
            title = item.findtext(
                "title",
                ""
            )

            link = item.findtext(
                "link",
                ""
            )

            guid = item.findtext(
                "guid",
                ""
            )

            description = item.findtext(
                "description",
                ""
            )

            pub_date = item.findtext(
                "pubDate",
                ""
            )

            if not link:
                continue

            try:
                published = parsedate_to_datetime(
                    pub_date
                )

                if published.tzinfo is None:
                    published = published.replace(
                        tzinfo=JST
                    )

            except Exception:
                continue

            items[link] = {
                "title": title,
                "link": link,
                "guid": guid,
                "published": published,
                "description": description,
            }

    except Exception as e:
        print(
            f"既存RSS読込エラー: {e}"
        )

    return items


def write_rss(items):
    rss = ET.Element(
        "rss",
        version="2.0"
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = FEED_TITLE

    ET.SubElement(
        channel,
        "link"
    ).text = SOURCE_URL

    ET.SubElement(
        channel,
        "description"
    ).text = FEED_DESCRIPTION

    ET.SubElement(
        channel,
        "language"
    ).text = "ja"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = format_datetime(
        datetime.now(JST)
    )

    sorted_items = sorted(
        items.values(),
        key=lambda x: x["published"],
        reverse=True
    )

    for data in sorted_items:
        item = ET.SubElement(
            channel,
            "item"
        )

        ET.SubElement(
            item,
            "title"
        ).text = data["title"]

        ET.SubElement(
            item,
            "link"
        ).text = data["link"]

        guid = ET.SubElement(
            item,
            "guid"
        )

        guid.set(
            "isPermaLink",
            "false"
        )

        guid.text = data["guid"]

        ET.SubElement(
            item,
            "pubDate"
        ).text = format_datetime(
            data["published"]
        )

        ET.SubElement(
            item,
            "description"
        ).text = data["description"]

    tree = ET.ElementTree(rss)

    try:
        ET.indent(
            tree,
            space="  "
        )
    except AttributeError:
        pass

    tree.write(
        RSS_FILE,
        encoding="utf-8",
        xml_declaration=True
    )


def main():
    print("=" * 70)
    print(
        "大阪体育大学ラグビー部 "
        "クラブニュース RSS"
    )
    print("=" * 70)

    existing = load_existing_items()

    print(
        f"既存RSS件数: {len(existing)}"
    )

    try:
        html = fetch_page()

        current_items = parse_articles(
            html
        )

        print(
            f"現在ページ取得件数: "
            f"{len(current_items)}件"
        )

        if not current_items:
            raise RuntimeError(
                "クラブニュースの記事を"
                "1件も抽出できませんでした。"
            )

        current = {
            item["link"]: item
            for item in current_items
        }

        new_links = (
            set(current.keys())
            - set(existing.keys())
        )

        print(
            f"新規記事: "
            f"{len(new_links)}件"
        )

        merged = dict(existing)
        merged.update(current)

        print(
            f"累積RSS件数: "
            f"{len(merged)}件"
        )

        print()

        sorted_current = sorted(
            current_items,
            key=lambda x: x["published"],
            reverse=True
        )

        for item in sorted_current[:30]:
            print(
                f"{item['published'].strftime('%Y-%m-%d')} "
                f"{item['title']}"
            )

        write_rss(
            merged
        )

        print()
        print(
            f"保存完了: "
            f"{RSS_FILE} "
            f"({len(merged)}件)"
        )

    except Exception:
        print()
        print(
            "取得・解析に失敗したため、"
            "既存RSSは変更しません。"
        )
        raise


if __name__ == "__main__":
    main()