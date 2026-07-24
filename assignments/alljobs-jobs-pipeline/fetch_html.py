import json
import sys

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_html(url: str, output_path: str) -> None:
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(response.text)


def _find_by_class_prefix(tag, prefix):
    return tag.find("div", class_=lambda c: c and any(cl.startswith(prefix) for cl in c.split()))


def _find_by_classes(tag, classes):
    return tag.find(class_=lambda c: c and any(cl in classes for cl in c.split()))


def _text(el):
    return el.get_text(" ", strip=True) if el else None


def parse_jobs(html_path: str, output_path: str) -> None:
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    jobs = []
    for box in soup.find_all("div", class_="job-box"):
        title_el = _find_by_class_prefix(box, "job-content-top-title")
        h2 = title_el.find("h2") if title_el else None

        location_el = _find_by_classes(
            box,
            (
                "job-content-top-location-ltr",
                "job-content-top-location",
                "job-regions-content",
            ),
        )
        type_el = _find_by_classes(
            box, ("job-content-top-type", "job-content-top-type-ltr")
        )

        jobs.append(
            {
                "time": _text(box.find(class_="job-content-top-date")),
                "title": _text(h2),
                "company": _text(box.find(class_="T14")),
                "location": _text(location_el),
                "type": _text(type_el),
                "description": _text(box.find(class_="job-content-top-desc")),
            }
        )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    fetch_html("https://www.alljobs.co.il/SearchResultsGuest.aspx?page=1&position=235&type=&city=&region=", "alljobs.html")
    parse_jobs("alljobs.html", "jobs.json")
