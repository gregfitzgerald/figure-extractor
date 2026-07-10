#!/usr/bin/env python3
"""Acceptance tests for the META core — the APPROVED test cases (TC1-TC8) as runnable checks.
Run: python3 meta-analysis/test_metalib.py"""
import metalib as M

ok = 0
def check(c, msg):
    global ok
    assert c, "FAIL: " + msg
    ok += 1; print("PASS", msg)


def study(sid, arms, mods=None, dep=None, prov=None, outcome=None):
    return {"studyId": sid, "label": sid, "arms": arms, "moderators": mods or {},
            "dependency": dep or {"clusterId": "", "sharesControlWith": []},
            "provenance": prov or {"source": "figure", "extractedBy": "agent", "reviewStatus": "confirmed"},
            "outcome": outcome or {"assay": "ELISA"}}

def article(aid, studies, status="included", **kw):
    a = {"articleId": aid, "screening": {"status": status}, "riskOfBias": {"overall": "some concerns"},
         "studies": studies}
    a.update(kw); return a


# TC1 — single experiment, mean +/- SEM
tc1 = article("smith19", [study("smith19-e1",
    {"intervention": {"label": "run", "n": 10, "mean": 32.4, "dispersion": 3.1, "dispersionType": "SEM"},
     "control": {"label": "sed", "n": 10, "mean": 24.1, "dispersion": 2.8, "dispersionType": "SEM"}})])
rows = M.flatten({"articles": [tc1]})
check(len(rows) == 1, "TC1: one study")
check(abs(rows[0]["sd_int"] - 3.1 * (10 ** 0.5)) < 1e-3 and abs(rows[0]["sd_ctrl"] - 2.8 * (10 ** 0.5)) < 1e-3,
      "TC1: SEM->SD via *sqrt(n)")
check(abs(rows[0]["yi"] - 0.851) < 0.01 and abs(rows[0]["vi"] - 0.204) < 0.01, f"TC1: Hedges g {rows[0]['yi']}, var {rows[0]['vi']}")
check(rows[0]["clusterId"] == "smith19", "TC1: clusterId = articleId")

# TC2 — 3 studies per article, shared control
def arms(mean_i):
    return {"intervention": {"n": 10, "mean": mean_i, "dispersion": 3.0, "dispersionType": "SEM"},
            "control": {"n": 10, "mean": 24.0, "dispersion": 3.0, "dispersionType": "SEM"}}
tc2 = article("lee20", [
    study("lee20-2wk", arms(27), {"durationWeeks": 2}, {"clusterId": "lee20", "sharesControlWith": ["lee20-4wk", "lee20-8wk"]}),
    study("lee20-4wk", arms(30), {"durationWeeks": 4}, {"clusterId": "lee20", "sharesControlWith": ["lee20-2wk", "lee20-8wk"]}),
    study("lee20-8wk", arms(33), {"durationWeeks": 8}, {"clusterId": "lee20", "sharesControlWith": ["lee20-2wk", "lee20-4wk"]}),
])
r2 = M.flatten({"articles": [tc2]})
check(len(r2) == 3 and len({x["clusterId"] for x in r2}) == 1, "TC2: 3 studies, one cluster (article!=study)")
check(all(x["sharesControlWith"] for x in r2), "TC2: shared-control dependency recorded")

# TC3 — subregion moderator + dependency
tc3 = article("vivar21", [
    study("vivar21-d", arms(31), {"subregion": "dorsal"}, {"clusterId": "vivar21", "sharesControlWith": ["vivar21-v"]}),
    study("vivar21-v", arms(28), {"subregion": "ventral"}, {"clusterId": "vivar21", "sharesControlWith": ["vivar21-d"]}),
])
r3 = M.flatten({"articles": [tc3]})
check(len(r3) == 2 and {x["subregion"] for x in r3} == {"dorsal", "ventral"}, "TC3: subregion moderator on 2 studies")

# TC4 — excluded article contributes 0 studies
tc4 = article("mrna22", [study("mrna22-e1", arms(30))], status="excluded")
tc4["screening"]["reasonExcluded"] = "outcome: mRNA not protein"
check(M.flatten({"articles": [tc4]}) == [], "TC4: excluded article -> 0 studies")

# TC5 — SD (not SEM): no sqrt(n)
sd_arm = {"n": 8, "mean": 30.0, "dispersion": 6.0, "dispersionType": "SD"}
check(abs(M.arm_sd(sd_arm) - 6.0) < 1e-9, "TC5: SD used directly (no *sqrt(n))")

# TC6 — box plot median/IQR -> mean/SD
mean, sd = M.box_to_mean_sd(20.0, 25.0, 32.0)
check(abs(mean - (20 + 25 + 32) / 3) < 1e-9 and abs(sd - (32 - 20) / 1.35) < 1e-9, "TC6: median/IQR -> mean/SD (Wan)")
box_study = study("box-e1", {"intervention": {"n": 12, "q1": 20, "median": 25, "q3": 32},
                             "control": {"n": 12, "q1": 14, "median": 18, "q3": 24}})
check(M.study_effect(box_study) is not None, "TC6: box arms yield an effect")

# TC7 — ambiguous dispersion -> quarantined (needs review), excluded from primary table
amb = {"n": 10, "mean": 30.0, "dispersion": 4.0, "dispersionType": "unknown"}
check(M.arm_sd(amb) is None, "TC7: unknown dispersion -> unresolvable")
tc7 = article("amb23", [study("amb23-e1",
    {"intervention": amb, "control": {"n": 10, "mean": 24.0, "dispersion": 4.0, "dispersionType": "unknown"}},
    prov={"reviewStatus": "needs-review"})])
check(M.flatten({"articles": [tc7]}) == [], "TC7: quarantined from primary table")
check(len(M.flatten({"articles": [tc7]}, include_needs_review=True)) == 1, "TC7: appears in sensitivity (include_needs_review)")

# TC8 — duplicate cohort de-duplication
corpus = {"articles": [article("conf24", [study("conf24-e1", arms(30))], cohortKey="cohortX"),
                       article("jrnl24", [study("jrnl24-e1", arms(30))], cohortKey="cohortX")]}
M.dedupe_cohorts(corpus)
statuses = [a["screening"]["status"] for a in corpus["articles"]]
check(statuses.count("included") == 1 and statuses.count("excluded") == 1, "TC8: duplicate cohort -> one excluded")

# end-to-end: a studies.csv is produced
csv_text = M.studies_csv(M.flatten({"articles": [tc1, tc2, tc3]}))
check(csv_text.splitlines()[0].startswith("articleId,studyId") and len(csv_text.strip().splitlines()) == 1 + 6,
      "studies.csv: header + 6 study rows (1+3+2)")

print(f"\nMETA-LIB ACCEPTANCE (TC1-TC8): {ok} checks PASS")
