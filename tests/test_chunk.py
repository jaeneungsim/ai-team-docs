from team_docs import chunk
from team_docs.chunk import MAX_CHARS, MIN_CHARS, Chunk


def section(name: str, size: int) -> str:
    return f"## {name}\n\n" + ("word " * (size // 5)).strip()


def test_each_long_enough_section_is_a_chunk():
    text = section("One", 400) + "\n\n" + section("Two", 400)
    assert [piece.heading for piece in chunk.split(text)] == ["One", "Two"]
    assert not chunk.split(text)[0].text.startswith("## One")  # the heading is in `heading`, not repeated


def test_short_sections_join_the_next_one():
    text = "Intro.\n\n" + section("Short", 50) + "\n\n" + section("Long", 400)
    pieces = chunk.split(text)
    assert [piece.heading for piece in pieces] == [""]
    assert pieces[0].text.startswith("Intro.\n\n## Short\n\nword")
    assert "## Long" in pieces[0].text


def test_a_short_last_section_joins_the_chunk_before_it():
    text = section("Long", 400) + "\n\n" + section("Tail", 40)
    pieces = chunk.split(text)
    assert [piece.heading for piece in pieces] == ["Long"]
    assert pieces[0].text.endswith("## Tail\n\nword word word word word word word word")


def test_long_sections_split_between_paragraphs_and_not_inside_code():
    code = "```bash\n" + "\n".join(f"echo {n}" for n in range(300)) + "\n```"
    text = "## Big\n\n" + "\n\n".join([("para " * 100).strip()] * 4) + "\n\n" + code
    pieces = chunk.split(text)
    assert len(pieces) > 1
    assert all(len(piece.text) <= MAX_CHARS for piece in pieces)
    assert all(piece.heading == "Big" for piece in pieces)
    whole_code = [piece.text for piece in pieces if piece.text.startswith("```bash")]
    assert whole_code and whole_code[0].endswith("```")


def test_hash_lines_inside_code_are_not_headings():
    text = "## Run it\n\n```bash\n# not a heading\nmake\n```\n\n" + ("more " * 80)
    assert [piece.heading for piece in chunk.split(text)] == ["Run it"]


def test_index_text_names_the_page_and_section():
    text = chunk.index_text("Deploy to dev", Chunk("Check a deploy", "Body"))
    assert text == "Deploy to dev > Check a deploy\n\nBody"
    assert chunk.index_text("Glossary", Chunk("", "Body")) == "Glossary\n\nBody"


def test_limits():
    assert MIN_CHARS < MAX_CHARS
