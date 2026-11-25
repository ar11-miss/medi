"""RAG tests with a fake LLM (no Groq key needed)."""
import json

from app.rag import RemedyRAG, Retriever, load_kb, personalise, select_entry

KB = load_kb()
ADULT = {"age_years": 30, "sex": "male", "allergies": [], "current_medicines": [], "conditions": []}


class FakeLLM:
    def __init__(self, pick=None, medicines=None, fail=False):
        self.pick = pick
        self.medicines = medicines
        self.fail = fail
        self.prompts = []

    def chat_json(self, system, messages, temperature=0.0):
        self.prompts.append(system)
        if self.fail:
            raise RuntimeError("API down")
        if "knowledge base" in system and "Candidates" in system:
            return {"id": self.pick, "confidence": 0.9}
        meds = self.medicines if self.medicines is not None else []
        return {"summary": "Looks like a cold.", "home_care": ["Rest"], "medicines": meds,
                "see_doctor_if": ["Fever over 3 days"]}


def entry(eid):
    return next(e for e in KB["entries"] if e["id"] == eid)


def test_kb_is_consistent():
    ids = [e["id"] for e in KB["entries"]]
    assert len(ids) == len(set(ids)) == 12
    for e in KB["entries"]:
        for m in e["medicines"]:
            assert m in KB["medicines"], f"{e['id']} uses unknown medicine {m}"
        assert e["home_care"] and e["see_doctor_if"]


def test_retrieval_works_in_three_languages():
    r = Retriever(KB, "tfidf")
    assert r.search("my throat hurts when I swallow")[0]["id"] == "sore_throat"
    assert r.search("खाने के बाद पेट में जलन")[0]["id"] == "acidity"
    assert r.search("आज दोन वेळा जुलाब झाले")[0]["id"] == "loose_motions"
    assert r.search("machhar ke katne se khujli")[0]["id"] == "insect_bite"


def test_personalise_removes_unsuitable_medicines():
    headache = entry("tension_headache")  # paracetamol + ibuprofen
    p = personalise(headache, KB, dict(ADULT, conditions=["stomach ulcer"]))
    assert [m["id"] for m in p["allowed"]] == ["paracetamol"]
    assert "stomach ulcer" in p["excluded"][0]["reason"]

    p = personalise(headache, KB, dict(ADULT, sex="female", pregnant=True))
    assert [m["id"] for m in p["allowed"]] == ["paracetamol"]
    assert "pregnant" in p["allowed"][0]["note"]

    p = personalise(headache, KB, dict(ADULT, allergies=["Crocin"]))
    assert [m["id"] for m in p["allowed"]] == ["ibuprofen"]

    p = personalise(headache, KB, dict(ADULT, current_medicines=["warfarin"]))
    assert p["allowed"] == []


def test_children_and_unknown_age():
    loose = entry("loose_motions")  # ORS is fine for all ages
    p = personalise(loose, KB, dict(ADULT, age_years=4), "mr")
    assert [m["id"] for m in p["allowed"]] == ["ors"]
    assert "फार्मासिस्ट" in p["notes"][0]
    p = personalise(entry("common_cold"), KB, {"age_years": 6})
    assert [m["id"] for m in p["allowed"]] == ["saline_drops"]
    p = personalise(entry("common_cold"), KB, {})
    assert p["allowed"] == [] and "Age not known" in p["notes"][0]


def test_groq_picks_or_says_none():
    cands = Retriever(KB, "tfidf").search("runny nose and sneezing")
    e, conf, how = select_entry(FakeLLM(pick="common_cold"), "q", cands)
    assert e["id"] == "common_cold" and how == "groq"
    e, _, _ = select_entry(FakeLLM(pick="none"), "q", cands)
    assert e is None
    # an id that wasn't a candidate -> fall back to retrieval
    e, _, how = select_entry(FakeLLM(pick="made_up"), "q", cands)
    assert e["id"] == cands[0]["id"] and how == "retrieval"


def test_grounding_check_drops_made_up_medicines():
    llm = FakeLLM(pick="common_cold", medicines=[
        {"id": "paracetamol", "how_to_take": "1 tablet every 6 hours", "note": ""},
        {"id": "amoxicillin", "how_to_take": "500 mg", "note": ""}])
    rag = RemedyRAG(llm=llm, retrieval_mode="tfidf")
    r = rag.get_remedies(text="runny nose, sneezing", profile=ADULT, triage={"level": "green"})
    assert r["matched"] and r["entry_id"] == "common_cold"
    assert [m["id"] for m in r["medicines"]] == ["paracetamol"]
    assert r["ungrounded_dropped"] == ["amoxicillin"]
    # the answer prompt contained only the retrieved entry
    assert "steam inhalation" in llm.prompts[-1] and "ORS" not in llm.prompts[-1]


def test_orange_and_red_get_no_home_remedies():
    rag = RemedyRAG(llm=FakeLLM(pick="common_cold"), retrieval_mode="tfidf")
    for lvl in ("orange", "red"):
        r = rag.get_remedies(text="cold", profile=ADULT, triage={"level": lvl})
        assert r["skipped"] and not r["matched"]


def test_works_without_groq():
    rag = RemedyRAG(llm=FakeLLM(fail=True), retrieval_mode="tfidf")
    r = rag.get_remedies(text="I cut my finger while cooking, bleeding stopped", profile=ADULT,
                         triage={"level": "green"})
    assert r["matched"] and r["entry_id"] == "minor_cut"
    assert r["generated_by"] == "template" and r["medicines"][0]["id"] == "povidone_iodine"


def test_no_match_below_threshold_without_groq():
    rag = RemedyRAG(llm=None, retrieval_mode="tfidf")
    r = rag.get_remedies(text="knee replacement surgery next month", profile=ADULT, triage={"level": "green"})
    assert not r["matched"]
    json.dumps(r)  # result is JSON-serialisable for the frontend
