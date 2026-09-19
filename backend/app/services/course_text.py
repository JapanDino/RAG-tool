"""Preserve instructional blocks without splitting sentences at inline HTML."""

from bs4 import BeautifulSoup


def extract_course_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(
        [
            "p",
            "div",
            "section",
            "article",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "tr",
            "blockquote",
            "pre",
        ]
    ):
        block.insert_before("\n")
        block.append("\n")
    return "\n".join(
        " ".join(line.split())
        for line in soup.get_text(separator=" ").splitlines()
        if line.strip()
    )
