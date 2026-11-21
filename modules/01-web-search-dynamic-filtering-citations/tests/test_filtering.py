from cited_search.filtering import filtering_steps, format_filtering_steps
from tests.conftest import load_message


def test_basic_search_has_no_filtering_steps(direct_message):
    assert filtering_steps(direct_message.content) == ()


def test_extracts_the_code_claude_wrote_for_each_step():
    steps = filtering_steps(load_message("dynamic_two_steps").content)

    assert len(steps) == 2
    assert steps[0].code.startswith('r = await web_search({"query": "latest python release"})')
    assert "json.loads(r)" in steps[1].code


def test_links_searches_to_the_step_that_ran_them():
    steps = filtering_steps(load_message("dynamic_two_steps").content)

    assert steps[0].queries == ("latest python release",)
    assert steps[1].queries == ()


def test_output_of_a_step_that_called_web_search_comes_back_encrypted():
    first, second = filtering_steps(load_message("dynamic_two_steps").content)

    assert first.is_encrypted and first.stdout is None
    assert first.return_code == 1
    assert "TypeError" in first.stderr
    assert not second.is_encrypted
    assert second.stdout == "Download Python  Python 3.15.2 is the latest stable release."


def test_format_shows_code_queries_and_output():
    output = format_filtering_steps(filtering_steps(load_message("dynamic_two_steps").content))

    assert "Filtering step 1 of 2" in output
    assert "for x in r[:6]:" in output
    assert 'searched: "latest python release"' in output
    assert "encrypted by the API" in output
    assert "failed (return code 1): TypeError: string indices must be integers" in output
    assert "Python 3.15.2 is the latest stable release." in output


def test_format_truncates_long_outputs():
    message = load_message("dynamic_two_steps")
    message.content[5].content.stdout = "x" * 5000

    output = format_filtering_steps(filtering_steps(message.content), max_output_chars=100)

    assert "x" * 100 in output
    assert "x" * 101 not in output
    assert "4,900 more characters" in output


def test_format_says_when_there_is_no_filtering_code(direct_message):
    output = format_filtering_steps(filtering_steps(direct_message.content))

    assert "No filtering code" in output
