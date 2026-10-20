import xml.etree.ElementTree as ET

import pytest
from scripts.demo_docs import load_docs, split_front_matter
from scripts.md_to_storage import convert

NAMESPACES = 'xmlns:ac="http://atlassian.com/content" xmlns:ri="http://atlassian.com/resource/identifier"'


def parse(storage: str) -> ET.Element:
    """Storage format is XHTML with ac: and ri: elements; it has to be well-formed XML."""
    return ET.fromstring(f"<root {NAMESPACES}>{storage}</root>")


def test_panel_keeps_its_title():
    out = convert("::: warning Read this first\nCannot be undone.\n:::\n")
    assert out.startswith('<ac:structured-macro ac:name="warning"><ac:parameter ac:name="title">Read this first')
    assert "<p>Cannot be undone.</p>" in out
    parse(out)


def test_panel_without_title_has_no_title_parameter():
    out = convert(":::tip\nItem 43 has no stock.\n:::\n")
    assert '<ac:structured-macro ac:name="tip"><ac:rich-text-body>' in out


def test_expand_wraps_markdown_inside():
    out = convert("::: expand Item API\n```bash\nuv venv\n```\n:::\n")
    assert '<ac:structured-macro ac:name="expand"><ac:parameter ac:name="title">Item API</ac:parameter>' in out
    assert '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">bash</ac:parameter>' in out
    parse(out)


def test_code_keeps_text_and_survives_cdata_end():
    out = convert("```sh\necho ']]>' && cat <file>\n```\n")
    assert '<ac:parameter ac:name="language">bash</ac:parameter>' in out
    root = parse(out)
    assert "".join(root.itertext()).strip() == "bash" + "echo ']]>' && cat <file>"


def test_page_link_with_and_without_text():
    out = convert("See [[Error codes]] and [[ADR-003 Error response format|the format]].")
    assert '<ri:page ri:content-title="Error codes" />' in out
    assert '<ri:page ri:content-title="ADR-003 Error response format" />' in out
    assert "<![CDATA[the format]]>" in out
    parse(out)


def test_status_lozenge():
    out = convert("{status:Superseded|Grey} · Decided 2026-10-11")
    assert '<ac:parameter ac:name="colour">Grey</ac:parameter><ac:parameter ac:name="title">Superseded' in out


def test_toc_and_children_macros():
    out = convert("{toc}\n\nText\n\n{children}\n")
    assert '<ac:structured-macro ac:name="toc" />' in out
    assert '<ac:structured-macro ac:name="children" />' in out


def test_table_rows_share_one_tbody():
    out = convert("| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert out.startswith("<table><tbody>")
    assert "<thead>" not in out and out.count("<tbody>") == 1
    parse(out)


def test_text_is_escaped():
    out = convert('Use `x < 1` & "quotes"')
    assert "<code>x &lt; 1</code> &amp;" in out
    parse(out)


def test_front_matter():
    meta, body = split_front_matter("---\ntitle: Runbooks\nparent: Inventory Team\n---\n\nBody\n")
    assert meta == {"title": "Runbooks", "parent": "Inventory Team"}
    assert body == "Body\n"
    with pytest.raises(ValueError):
        split_front_matter("no front matter")


@pytest.mark.parametrize("stage", ["v1", "v2"])
def test_every_demo_doc_converts_to_well_formed_storage(stage):
    docs = load_docs(stage)
    assert docs[0].home
    seen = set()
    for doc in docs:
        assert doc.home or doc.parent in seen, f"{doc.title} comes before its parent"
        seen.add(doc.title)
        parse(convert(doc.body))


def test_page_links_point_at_existing_titles():
    docs = load_docs("v1")
    titles = {doc.title for doc in docs}
    for doc in docs:
        for link in ET.fromstring(f"<root {NAMESPACES}>{convert(doc.body)}</root>").iter(
            "{http://atlassian.com/resource/identifier}page"
        ):
            target = link.get("{http://atlassian.com/resource/identifier}content-title")
            assert target in titles, f"{doc.title} links to missing page {target!r}"
