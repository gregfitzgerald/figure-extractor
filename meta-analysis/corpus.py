#!/usr/bin/env python3
"""
Corpus step: run the APPROVED PubMed search and fetch candidate records (title, abstract,
metadata) into meta-analysis/corpus/candidates.json. This is the "identification" box of PRISMA.

Uses NCBI E-utilities (no key needed; email set for the polite pool). Screening happens next
(screen.py): an agent reads each title+abstract against the protocol's inclusion/exclusion.
"""
import json, os, pathlib, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET

# NCBI asks API users to identify themselves (the "polite pool" -- higher rate limits, and they can
# contact you before blocking a runaway script). Set NCBI_EMAIL to your own address before running.
EMAIL = os.environ.get("NCBI_EMAIL", "")
TOOL = "figure-extractor-meta"
OUT = pathlib.Path(__file__).resolve().parent / "corpus"
OUT.mkdir(exist_ok=True)

# Tightened search (v1.1): restrict to VOLUNTARY running + hippocampal BDNF in title/abstract,
# drop reviews. Cuts the disease-model/treadmill noise the broad string surfaced.
QUERY = ('(hippocamp*[tiab]) AND (BDNF[tiab] OR "brain-derived neurotrophic factor"[tiab]) AND '
         '("wheel running"[tiab] OR "running wheel"[tiab] OR "voluntary running"[tiab] OR '
         '"voluntary wheel"[tiab] OR "voluntary exercise"[tiab]) AND '
         '(rat[tiab] OR rats[tiab] OR mouse[tiab] OR mice[tiab] OR rodent*[tiab] OR murine[tiab]) '
         'NOT review[pt]')
# Per-request page size, NOT a cap on the corpus. It used to be a cap: esearch returns
# most-recent-first, so retmax=120 against 204 hits silently dropped the OLDEST 85 -- the
# entire pre-mid-2013 literature, including the foundational Neeper / Russo-Neustadt-era
# studies this question is built on. The fetched corpus spanned 2013-2026 and nothing said
# so; STATUS.md called it "the tightened set". That is a recency selection bias baked into
# the sample before a single figure is read. esearch is now paginated to completion.
PAGE = 200


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": TOOL})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def esearch(query):
    """Every hit, paginated. Returns (ids, total) with len(ids) == total barring a race."""
    ids, total, start = [], None, 0
    while True:
        p = urllib.parse.urlencode({"db": "pubmed", "term": query, "retmax": PAGE,
                                    "retstart": start, "retmode": "json",
                                    "email": EMAIL, "tool": TOOL})
        data = json.loads(_get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + p))
        res = data["esearchresult"]
        if total is None:
            total = int(res["count"])
        batch = res.get("idlist") or []
        ids += batch
        start += len(batch)
        if not batch or start >= total:
            break
        time.sleep(0.4)
    return ids, total


def efetch(pmids):
    p = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml",
                                "email": EMAIL, "tool": TOOL})
    root = ET.fromstring(_get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + p))
    out = []
    for art in root.findall(".//PubmedArticle"):
        med = art.find(".//MedlineCitation")
        pmid = med.findtext("PMID", "")
        title = "".join(med.find(".//ArticleTitle").itertext()) if med.find(".//ArticleTitle") is not None else ""
        abstract = " ".join("".join(a.itertext()) for a in med.findall(".//Abstract/AbstractText"))
        year = med.findtext(".//JournalIssue/PubDate/Year") or med.findtext(".//JournalIssue/PubDate/MedlineDate", "")
        journal = med.findtext(".//Journal/Title", "")
        authors = []
        for a in med.findall(".//AuthorList/Author"):
            ln = a.findtext("LastName");
            if ln: authors.append(ln + (" " + a.findtext("Initials", "") if a.findtext("Initials") else ""))
        doi = ""
        # PubmedData/ArticleIdList ONLY. `.//ArticleIdList` also matches the id lists inside
        # this article's REFERENCE list, and with last-write-wins the DOI of a cited paper
        # overwrote the article's own. Measured on the live corpus: 3 of 16 sampled records
        # carried a reference's DOI (e.g. PMID 42000824 stored 10.14814/phy2.14287, a
        # Physiological Reports DOI from its bibliography). A wrong DOI breaks full-text
        # retrieval and deduplication downstream, and does so silently.
        for eid in art.findall("PubmedData/ArticleIdList/ArticleId"):
            if eid.get("IdType") == "doi": doi = eid.text
        out.append({"pmid": pmid, "title": title, "abstract": abstract,
                    "authors": "; ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""),
                    "year": year, "journal": journal, "doi": doi})
    return out


def main():
    ids, total = esearch(QUERY)
    print(f"esearch: {total} total hits; fetched {len(ids)} id(s)")
    if len(ids) < total:
        # Never leave a partial corpus looking complete -- that is how the era bias hid.
        raise SystemExit(
            f"esearch returned {len(ids)} of {total} hits. A partial corpus is a silent "
            "selection bias (esearch is most-recent-first, so the loss is by era). Re-run.")
    records, B = [], 20
    for i in range(0, len(ids), B):
        records += efetch(ids[i:i + B]); time.sleep(0.4)
    (OUT / "candidates.json").write_text(json.dumps(
        {"query": QUERY, "totalHits": total, "fetched": len(records),
         "complete": len(records) == total, "records": records}, indent=2))
    with_abs = sum(1 for r in records if r["abstract"])
    print(f"wrote {len(records)} candidates ({with_abs} with abstracts) -> corpus/candidates.json")
    for r in records[:5]:
        print(f"  {r['pmid']}  {r['year']}  {r['title'][:80]}")


if __name__ == "__main__":
    main()
