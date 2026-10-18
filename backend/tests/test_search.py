import pytest

from rag.hybrid import hybrid_search, keyword_tsquery
from schemas import PropertySearchParams


def refs(result):
    return [h.ref for h in result.hits]


def test_keyword_tsquery_uses_prefixes_and_drops_stopwords():
    assert keyword_tsquery("rooms near the BRAC campus") == "rooms:* | brac:* | campus:*"
    assert keyword_tsquery("ধানমন্ডি-তে ছাত্রীদের জন্য রুম") == "ধানমন্ডি:* | ছাত্রীদের:* | রুম:*"
    assert keyword_tsquery("a an the") is None


pytestmark_shared = pytest.mark.shared_seed


@pytestmark_shared
def test_finds_needle_listing(seeded, needles):
    res = hybrid_search(seeded, "rooftop garden with solar panels Aftabnagar", sources=["listing"], k=5)
    assert f"listing:{needles['listings']['ewu_rooftop_garden']}" in refs(res)[:3]


@pytestmark_shared
def test_structured_filters_are_hard_constraints(seeded, needles):
    res = hybrid_search(seeded, "rooftop garden with solar panels", sources=["listing"], k=20,
                        listing_filters=PropertySearchParams(max_price=10000))
    assert f"listing:{needles['listings']['ewu_rooftop_garden']}" not in refs(res)
    assert all(h.meta["price"] <= 10000 for h in res.hits)
    women = hybrid_search(seeded, "room", sources=["listing"], k=20,
                          listing_filters=PropertySearchParams(is_female_only=True))
    assert women.hits and all(h.meta["women_only"] for h in women.hits)


@pytestmark_shared
def test_bangla_query_finds_bangla_listing(seeded, needles):
    res = hybrid_search(seeded, "ধানমন্ডি লেক ছাত্রীদের রুম", sources=["listing"], k=5)
    assert f"listing:{needles['listings']['du_lakeview_bn']}" in refs(res)[:3]


@pytestmark_shared
def test_forum_search_and_one_hit_per_source(seeded, needles):
    res = hybrid_search(seeded, "Merul Badda Link Road flooding monsoon knee deep", sources=["post"], k=5)
    assert refs(res)[0] == f"post:{needles['posts']['merul_badda_flooding']}"
    assert len(refs(res)) == len(set(refs(res)))


@pytestmark_shared
def test_each_stage_can_be_disabled(seeded, needles):
    q = "rooftop garden with solar panels Aftabnagar"
    target = f"listing:{needles['listings']['ewu_rooftop_garden']}"
    for flags in ({"use_keyword": False}, {"use_vector": False}, {"use_rerank": False}):
        res = hybrid_search(seeded, q, sources=["listing"], k=5, **flags)
        assert target in refs(res), flags


@pytestmark_shared
def test_semantic_endpoint_returns_public_listing_summaries(client, seeded, needles):
    res = client.get("/api/search/semantic", params={"q": "female only room with meals Bashundhara",
                                                     "sources": "listing", "is_female_only": True, "k": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["stages"] == {"vector": True, "keyword": True, "rerank": True}
    hits = body["hits"]
    assert hits and all(h["listing"]["is_female_only"] for h in hits)
    assert f"listing:{needles['listings']['nsu_female_meals']}" in [h["ref"] for h in hits]
    assert "owner_phone" not in hits[0]["listing"] and "owner_email" not in hits[0]["listing"]
