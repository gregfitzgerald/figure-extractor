#!/usr/bin/env python3
"""resolve_pdfs.py -- map each figure-derived article's DOI to a local Zotero PDF.

Zotero stores every attachment under storage/<attachmentKey>/<filename>; the SQLite DB
links a parent item's DOI (itemData/fields) to its child PDF attachment (itemAttachments).
We open the DB READ-ONLY (URI mode) so it is safe while Zotero is running, build a
DOI -> PDF-path index, and resolve the articles.json worklist.

Output: pdf_map.json  { article_id: {doi, pdf, status} }.
status: ok | no-pdf-attachment | no-doi-match | file-missing.
"""
import json, os, pathlib, sqlite3, sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
ZOTERO_DB = os.environ.get("ZOTERO_DB", "/mnt/c/Users/gregs/Zotero/zotero.sqlite")
ZOTERO_STORAGE = os.environ.get("ZOTERO_STORAGE", "/mnt/c/Users/gregs/Zotero/storage")


def _norm(doi):
    return (doi or "").strip().lower().replace("https://doi.org/", "").replace("http://dx.doi.org/", "")


def build_index(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    doi_item = {}
    for r in con.execute(
        "SELECT i.itemID iid, idv.value v FROM items i "
        "JOIN itemData d ON i.itemID=d.itemID "
        "JOIN itemDataValues idv ON d.valueID=idv.valueID "
        "JOIN fields f ON d.fieldID=f.fieldID WHERE f.fieldName='DOI'"):
        doi_item[_norm(r["v"])] = r["iid"]
    att = defaultdict(list)
    for r in con.execute(
        "SELECT ia.parentItemID pid, ia.path path, it.key key FROM itemAttachments ia "
        "JOIN items it ON ia.itemID=it.itemID WHERE ia.contentType='application/pdf'"):
        att[r["pid"]].append((r["key"], r["path"]))
    con.close()
    return doi_item, att


def resolve_pdf(doi, doi_item, att):
    iid = doi_item.get(_norm(doi))
    if iid is None:
        return None, "no-doi-match"
    pdfs = att.get(iid, [])
    if not pdfs:
        return None, "no-pdf-attachment"
    for key, path in pdfs:
        if path and path.startswith("storage:"):
            full = os.path.join(ZOTERO_STORAGE, key, path[len("storage:"):])
            if os.path.exists(full):
                return full, "ok"
    return None, "file-missing"


def main():
    articles = json.loads((HERE / "articles.json").read_text())
    doi_item, att = build_index(ZOTERO_DB)
    print(f"Zotero index: {len(doi_item)} DOIs, {len(att)} items with a PDF child\n")
    out, ok = {}, 0
    for a, meta in sorted(articles.items()):
        pdf, status = resolve_pdf(meta["doi"], doi_item, att)
        out[a] = {"doi": meta["doi"], "pdf": pdf, "status": status}
        ok += status == "ok"
        print(f"{a:24s} {status:18s} {meta['doi']}")
    (HERE / "pdf_map.json").write_text(json.dumps(out, indent=2))
    print(f"\nRESOLVED {ok}/{len(articles)} articles to a local PDF")
    print(f"[written] {HERE/'pdf_map.json'}")


if __name__ == "__main__":
    main()
