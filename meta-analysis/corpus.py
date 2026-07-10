#!/usr/bin/env python3
"""
Corpus step: run the APPROVED PubMed search and fetch candidate records (title, abstract,
metadata) into meta-analysis/corpus/candidates.json. This is the "identification" box of PRISMA.

Uses NCBI E-utilities (no key needed; email set for the polite pool). Screening happens next
(screen.py): an agent reads each title+abstract against the protocol's inclusion/exclusion.
"""
import json, pathlib, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET

EMAIL = "greg.s.fitzgerald@gmail.com"
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
RETMAX = 120  # fetch the whole tightened set


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": TOOL})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def esearch(query):
    p = urllib.parse.urlencode({"db": "pubmed", "term": query, "retmax": RETMAX,
                                "retmode": "json", "email": EMAIL, "tool": TOOL})
    data = json.loads(_get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + p))
    return data["esearchresult"]["idlist"], int(data["esearchresult"]["count"])


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
        for eid in art.findall(".//ArticleIdList/ArticleId"):
            if eid.get("IdType") == "doi": doi = eid.text
        out.append({"pmid": pmid, "title": title, "abstract": abstract,
                    "authors": "; ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""),
                    "year": year, "journal": journal, "doi": doi})
    return out


def main():
    ids, total = esearch(QUERY)
    print(f"esearch: {total} total hits; fetching {len(ids)} (retmax={RETMAX})")
    records, B = [], 20
    for i in range(0, len(ids), B):
        records += efetch(ids[i:i + B]); time.sleep(0.4)
    (OUT / "candidates.json").write_text(json.dumps(
        {"query": QUERY, "totalHits": total, "fetched": len(records), "records": records}, indent=2))
    with_abs = sum(1 for r in records if r["abstract"])
    print(f"wrote {len(records)} candidates ({with_abs} with abstracts) -> corpus/candidates.json")
    for r in records[:5]:
        print(f"  {r['pmid']}  {r['year']}  {r['title'][:80]}")


if __name__ == "__main__":
    main()
