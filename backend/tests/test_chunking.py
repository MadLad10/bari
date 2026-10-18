from types import SimpleNamespace as NS

from rag.chunking import detect_lang, listing_chunks, post_chunks, safety_chunks, split_text


def test_split_short_text_is_one_chunk():
    assert split_text("Short post.") == ["Short post."]


def test_split_long_text_on_sentences_including_bangla_danda():
    english = " ".join(f"Sentence number {i} talks about flooding in Badda." for i in range(40))
    chunks = split_text(english, limit=300)
    assert len(chunks) > 3 and all(len(c) <= 300 for c in chunks)
    assert all(c.endswith(".") for c in chunks)
    bangla = "".join(f"বাক্য {i}: বর্ষায় গলিতে পানি জমে। " for i in range(40))
    bn_chunks = split_text(bangla, limit=200)
    assert len(bn_chunks) > 3 and all(c.endswith("।") for c in bn_chunks)


def test_split_overlaps_one_sentence():
    text = " ".join(f"S{i} is a short sentence here." for i in range(30))
    chunks = split_text(text, limit=200)
    last_of_first = chunks[0].split(". ")[-1].rstrip(".")
    assert chunks[1].startswith(last_of_first)


def test_listing_chunk_has_context_and_no_contact_details():
    p = NS(id=7, title="Room near NSU", description="Quiet room.", property_type="room", listing_type="sublet",
           rental_type="monthly", furnishing="semi_furnished", price=6500, bedrooms=1, area="Bashundhara",
           city="Dhaka", nearby_university="North South University", university_distance_km=0.5,
           is_female_only=True, amenities=["WiFi", "CCTV"], owner_phone="01700000000",
           owner_email="o@example.com", created_at=None)
    [c] = listing_chunks(p)
    assert c.source_type == "listing" and c.property_id == 7
    assert "Listing #7" in c.content and "women-only" in c.content and "North South University" in c.content
    assert "৳6,500/month" in c.content
    assert "01700000000" not in c.content and "o@example.com" not in c.content


def test_post_chunks_repeat_header():
    post = NS(id=3, title="Badda floods", body="\n\n".join(["Para one about water. " * 20] * 4),
              post_type="experience", area="Badda", nearby_university="BRAC University", property_id=None,
              created_at=None)
    chunks = post_chunks(post)
    assert len(chunks) > 1
    assert all(c.content.startswith("Forum post #3 [experience] Badda floods (Badda)") for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_safety_vote_without_comment_is_not_indexed():
    prop = NS(id=1, title="Flat", area="Gulshan", nearby_university=None)
    assert safety_chunks(NS(id=1, rating=4, comment=None, created_at=None), prop) == []
    [c] = safety_chunks(NS(id=2, rating=2, comment="Dark lane", created_at=None), prop)
    assert c.content.startswith("Safety rating 2/5 for listing #1")


def test_detect_lang():
    assert detect_lang("ধানমন্ডি লেকের পাশে রুম") == "bn"
    assert detect_lang("Room near Dhanmondi lake") == "en"
