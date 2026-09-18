"""render_edition.py -- the fixed layout, the escape discipline, the gate."""
from __future__ import annotations

import json

import pytest

from conftest import load_module

render = load_module("render_edition", "pt-edition/scripts/render_edition.py")


def edition_with_priority_and_weather():
    return edition(sections=[
        {"kind": "section", "title": "Weather", "desk": "weather", "body": "rain", "sources": []},
        {"kind": "section", "title": "Your #1 priority today", "desk": "priority",
         "headline": "Close the seed extension", "body": "Send the deck",
         "priority": {"why": [{"text": "t", "source_label": "calendar"}], "first_step": "x"},
         "sources": []},
    ])


EVENT = {"time": "10:00", "title": "Customer call: Dana", "note": "Go in with: what they use today"}


def priority_edition(**fields):
    p = {"why": [{"text": "t", "source_label": "calendar"}], "first_step": "x", **fields}
    return edition(sections=[{"kind": "section", "title": "P", "desk": "priority",
                              "body": "b", "priority": p, "sources": []}])


def edition(**overrides):
    base = {
        "date": "2026-09-11",
        "sections": [
            {
                "kind": "section",
                "topic_id": "t_8c1d",
                "title": "Weather in Sao Paulo",
                "body": "Rain in the afternoon.",
                "sources": ["https://example.com/weather"],
            }
        ],
    }
    base.update(overrides)
    return base


def write(tmp_path, data):
    path = tmp_path / "edition.json"
    path.write_text(json.dumps(data))
    return path


class TestValidate:
    def test_valid_is_silent(self):
        assert render.validate(edition()) == ""

    def test_missing_date(self):
        assert "date" in render.validate(edition(date="nope"))

    def test_impossible_date(self):
        assert "real calendar" in render.validate(edition(date="2026-02-30"))

    def test_sections_must_be_a_list(self):
        assert "sections is not a list" in render.validate(edition(sections={}))

    def test_unknown_kind(self):
        bad = edition(sections=[{"kind": "news", "title": "x", "body": "y"}])
        assert "kind" in render.validate(bad)

    def test_blank_title(self):
        bad = edition(sections=[{"kind": "section", "title": "", "body": "y"}])
        assert "title is blank" in render.validate(bad)

    def test_assignment_needs_run_on(self):
        bad = edition(sections=[{"kind": "assignment", "title": "x", "body": "y"}])
        assert "run_on is required" in render.validate(bad)

    def test_sources_must_be_strings(self):
        bad = edition(sections=[{"kind": "section", "title": "x", "body": "y",
                                 "sources": [1, 2]}])
        assert "sources" in render.validate(bad)

    def test_layout_must_be_main_or_sidebar(self):
        bad = edition(sections=[{
            "kind": "section", "title": "x", "body": "y", "layout": "top",
        }])
        assert "layout is not main|sidebar" in render.validate(bad)

    def test_desk_must_be_known(self):
        bad = edition(sections=[{
            "kind": "section", "title": "x", "body": "y", "desk": "gossip",
        }])
        assert "desk" in render.validate(bad)

    def test_desk_optional(self):
        assert render.validate(edition()) == ""
        assert render.validate(edition(sections=[{
            "kind": "section", "title": "x", "body": "y", "desk": "weather",
        }])) == ""

    def test_location_must_be_a_string_when_present(self):
        bad = edition(location=12)
        assert "location is not a string" in render.validate(bad)

    def test_layout_optional(self):
        assert render.validate(edition()) == ""
        assert render.validate(edition(sections=[{
            "kind": "section", "title": "x", "body": "y", "layout": "sidebar",
        }])) == ""

    def test_headline_must_be_a_string_when_present(self):
        bad = edition(sections=[{
            "kind": "section", "title": "x", "body": "y", "headline": 5,
        }])
        assert "headline is not a string" in render.validate(bad)

    def test_headline_optional(self):
        assert render.validate(edition()) == ""

    def test_topic_id_shape(self):
        bad = edition(sections=[{"kind": "section", "title": "x", "body": "y",
                                 "topic_id": "nope"}])
        assert "topic_id" in render.validate(bad)

    def test_forecast_only_on_weather(self):
        bad = edition(sections=[{
            "kind": "section", "title": "Diary", "desk": "calendar", "body": "c",
            "forecast": [{"day": "Tue", "date": "17/05", "icon": "sun", "high": 19, "low": 9}],
        }])
        assert "forecast is only valid on the weather desk" in render.validate(bad)

    def test_schedule_only_on_calendar(self):
        bad = edition(sections=[{
            "kind": "section", "title": "Weather", "desk": "weather", "body": "w",
            "schedule": [{"time": "9am", "title": "Sync", "icon": "meeting"}],
        }])
        assert "schedule is only valid on the calendar desk" in render.validate(bad)

    def test_messages_only_on_mail(self):
        bad = edition(sections=[{
            "kind": "section", "title": "Weather", "desk": "weather", "body": "w",
            "messages": [{"sender": "Ana", "subject": "Hi"}],
        }])
        assert "messages is only valid on the mail desk" in render.validate(bad)

    def test_schedule_icon_must_be_known(self):
        bad = edition(sections=[{
            "kind": "section", "title": "Diary", "desk": "calendar", "body": "c",
            "schedule": [{"time": "9am", "title": "Sync", "icon": "party"}],
        }])
        assert "icon is not one of" in render.validate(bad)

    def test_valid_strips_are_silent(self):
        assert render.validate(edition(sections=[
            {"kind": "section", "title": "Weather", "desk": "weather", "body": "w",
             "forecast": [{"day": "Tue", "date": "17/05", "icon": "rain", "high": 17, "low": 6}]},
            {"kind": "section", "title": "Diary", "desk": "calendar", "body": "c",
             "schedule": [{"time": "9am", "title": "Sync", "icon": "meeting"}]},
            {"kind": "section", "title": "Letters", "desk": "mail", "body": "m",
             "messages": [{"sender": "Ana", "subject": "Hi"}]},
        ])) == ""

    def test_priority_only_on_priority_desk(self):
        edition_data = edition(sections=[{
            "kind": "section", "title": "News", "desk": "news", "body": "n",
            "priority": {"why": [], "first_step": "x"},
        }])
        assert "priority is only valid on the priority desk" in render.validate(edition_data)

    def test_priority_why_must_have_one_to_three_sourced_items(self):
        p = {"why": [], "first_step": "Send the deck"}
        assert "priority.why needs 1 to 3 items" in render.validate(edition(sections=[{
            "kind": "section", "title": "P", "desk": "priority", "body": "b", "priority": p,
        }]))
        p = {"why": [{"text": "t"}], "first_step": "Send the deck"}
        assert "priority.why[0].source_label is blank" in render.validate(edition(sections=[{
            "kind": "section", "title": "P", "desk": "priority", "body": "b", "priority": p,
        }]))

    def test_priority_renders_headline_why_and_first_step(self):
        p = {"why": [{"text": "Q3 goal: raise $1.5M by Sep 30",
                      "source_label": "your file, Goals"}],
             "first_step": "Send the deck"}
        html = render.render_html(edition(sections=[{
            "kind": "section", "title": "Your #1 priority today", "desk": "priority",
            "headline": "Close the seed extension", "body": "Send the deck", "priority": p,
            "sources": [],
        }]), render.DEFAULT_MASTHEAD, "{{PRIORITY}}")
        assert "Close the seed extension" in html
        assert "Q3 goal: raise $1.5M by Sep 30 <span class=\"src\">— your file, Goals</span>" in html
        assert "Send the deck" in html
        assert "<script" not in html.lower()

    def test_priority_title_is_the_desk_title_not_python_text(self):
        html = render.render_html(edition(sections=[{
            "kind": "section", "title": "O que devo priorizar hoje?", "desk": "priority",
            "headline": "Close the seed extension", "body": "Send the deck",
            "priority": {"why": [{"text": "t", "source_label": "calendar"}],
                         "first_step": "x"},
            "sources": [],
        }]), render.DEFAULT_MASTHEAD, "{{PRIORITY_BLOCK}}")
        assert "O que devo priorizar hoje?" in html
        assert "priority-wrap" in html
        assert "Close the seed extension" in html

    def test_priority_title_empty_without_a_priority_desk(self):
        html = render.render_html(edition(), render.DEFAULT_MASTHEAD,
                                  "{{PRIORITY_BLOCK}}")
        assert html == ""

    def test_news_tag_renders_as_a_kicker_above_the_headline(self):
        html = render.render_html(edition(sections=[{
            "kind": "section", "title": "Markets rally", "desk": "news",
            "tag": "Economia", "body": "Stocks rose.",
            "sources": [],
        }]), render.DEFAULT_MASTHEAD, "{{LEAD}}")
        assert '<p class="kicker">Economia</p>' in html
        assert html.index("kicker") < html.index("Markets rally")
        assert '<span class="tag">Economia</span>' not in html

    def test_lead_body_runs_in_three_columns(self):
        html = render.render_html(edition(sections=[{
            "kind": "section", "title": "Lead", "desk": "news",
            "body": "One.\n\nTwo.\n\nThree.\n\nFour.",
            "sources": [],
        }]), render.DEFAULT_MASTHEAD, "{{LEAD}}")
        assert '<div class="lead-body">' in html
        assert html.count('<div class="lb-col">') == 3
        assert "dropcap" in html

    def test_news_well_lays_out_rows_of_three(self):
        sections = [{
            "kind": "section", "title": f"Story {i}", "desk": "news",
            "body": f"Body {i}.", "sources": [],
        } for i in range(7)]
        html = render.render_html(edition(sections=sections),
                                  render.DEFAULT_MASTHEAD,
                                  "{{SECTIONS}}")
        # 7 stories: 1 lead + 6 in the well = two rows of three. Each row
        # is its own table -- a single well-spanning table repaints
        # continued cell text in the wrong column in WeasyPrint 62.3
        # (measured), so rows must never split.
        assert html.count('<div class="news-cols">') == 2
        assert html.count("<article") == 6
        assert html.count('news-col--empty') == 0

    def test_news_well_pads_a_short_last_row(self):
        sections = [{
            "kind": "section", "title": f"Story {i}", "desk": "news",
            "body": f"Body {i}.", "sources": [],
        } for i in range(5)]
        html = render.render_html(edition(sections=sections),
                                  render.DEFAULT_MASTHEAD,
                                  "{{SECTIONS}}")
        # 1 lead + 4 in the well: a full row, then a row of one plus two
        # empty padding cells so column widths and rules stay put.
        assert html.count('<div class="news-cols">') == 2
        assert html.count('news-col--empty') == 2

    def test_desks_render_as_a_boxed_teaser_row(self):
        html = render.render_html(edition(sections=[
            {"kind": "section", "title": "Agenda", "desk": "calendar",
             "body": "c", "sources": []},
            {"kind": "section", "title": "Correio", "desk": "mail",
             "body": "m", "sources": []},
        ]), render.DEFAULT_MASTHEAD, "{{DESKS_INLINE}}")
        assert '<div class="desks-row">' in html
        assert html.count('<div class="desks-cell">') == 2

    @pytest.mark.parametrize("field, value, failure", [
        ("stage_label", " ", "priority.stage_label is blank"),
        ("stage_why", "", "priority.stage_why is blank"),
        ("yesterday", 3, "priority.yesterday is blank"),
        ("week", "  ", "priority.week is blank"),
        ("draft", ["Hey Raj"], "priority.draft is blank"),
        ("not_today", ["a", "b", "c"], "priority.not_today has more than 2 items"),
        ("not_today", [" "], "priority.not_today is not a list of non-blank strings"),
        ("who", "Raj", "priority.who is not a list of non-blank strings"),
        ("who", ["a", "b", "c", "d"], "priority.who has more than 3 items"),
        ("today", EVENT, "priority.today is not a list"),
        ("today", [EVENT] * 5, "priority.today has more than 4 items"),
        ("today", ["10:00 call"], "priority.today[0] is not an object"),
        ("today", [{**EVENT, "time": ""}], "priority.today[0].time is blank"),
        ("today", [{**EVENT, "title": " "}], "priority.today[0].title is blank"),
        ("today", [{"time": None, "title": "Call"}], "priority.today[0].note is blank"),
    ])
    def test_priority_field_shapes(self, field, value, failure):
        assert failure in render.validate(priority_edition(**{field: value}))

    def test_priority_renders_every_field_escaped_in_page_order(self):
        data = priority_edition(
            yesterday="1 booked (Dana <Acme>)", stage_label="Discovery",
            stage_why="No revenue yet & you still sell alone",
            today=[EVENT, {"time": None, "title": "Write the memo", "note": "Keep it short"}],
            week="Customer conversations: 2. The bar is tens.",
            who=["Raj — replied to the launch post", "Priya — trial user since Sep 9"],
            draft='Hey Raj, 20 minutes this week? "Tue" works.',
            not_today=["Hire a sales team"],
        )
        data["sections"][0]["headline"] = "Book 3 customer calls by Friday"
        assert render.validate(data) == ""
        html = render.render_html(data, render.DEFAULT_MASTHEAD, "{{PRIORITY}}")
        order = [
            "<h3>YESTERDAY</h3>", "1 booked (Dana &lt;Acme&gt;)",
            "STAGE · Discovery", "No revenue yet &amp; you still sell alone",
            "<h3>TODAY</h3>", "10:00", "Customer call: Dana", "Go in with: what they use today",
            "Write the memo", "<h3>THIS WEEK</h3>", "Customer conversations: 2.",
            "Book 3 customer calls by Friday", "→ x", "<h3>WHO</h3>", "Raj — replied",
            "Priya — trial user", "<h3>DRAFT</h3>", "Hey Raj, 20 minutes this week? &quot;Tue&quot;",
            "<h3>NOT TODAY</h3>", "Hire a sales team",
        ]
        positions = [html.index(text) for text in order]
        assert positions == sorted(positions)

    def test_priority_is_the_first_section_on_the_page(self):
        html = render.render_html(edition(sections=[
            {"kind": "section", "title": "News", "desk": "news", "body": "n", "sources": []},
            {"kind": "section", "title": "Weather", "desk": "weather", "body": "w", "sources": []},
            {"kind": "section", "title": "P", "desk": "priority", "body": "p", "sources": []},
        ]), render.DEFAULT_MASTHEAD, "{{PRIORITY}}{{WEATHER}}{{LEAD}}")
        assert html.index("section--priority") < html.index("section--weather")

    def test_priority_renders_exactly_once(self):
        html = render.render_html(
            edition_with_priority_and_weather(),
            render.DEFAULT_MASTHEAD,
            "{{PRIORITY}}{{DESKS_INLINE}}{{SIDEBAR}}",
        )
        assert html.count('section--priority"') == 1

    def test_priority_without_news_does_not_print_the_empty_budget_placeholder(self):
        html = render.render_html(
            edition_with_priority_and_weather(),
            render.DEFAULT_MASTHEAD,
            "{{LEAD}}{{PRIORITY}}",
        )
        assert "Nothing usable in the budget this time." not in html
        assert "Close the seed extension" in html
        assert html.count("<article") >= 1
        assert "{{LEAD}}" not in html
      

    def test_chat_edition_keeps_the_priority_body(self):
        p = {"why": [{"text": "t", "source_label": "calendar"}], "first_step": "x"}
        text = render.render_chat(edition(sections=[{
            "kind": "section", "title": "P", "desk": "priority", "body": "Send the deck",
            "priority": p, "sources": [],
        }]), render.DEFAULT_MASTHEAD)
        assert "Send the deck" in text


class TestMasthead:
    def test_json_cannot_name_the_paper(self):
        data = edition(masthead="The Fake Times")
        assert "The Fake Times" not in render.render_chat(data, render.masthead())
        assert render.DEFAULT_MASTHEAD in render.render_chat(data, render.masthead())

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PT_MASTHEAD", "The Daily Plow")
        assert render.masthead() == "The Daily Plow"

    def test_blank_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("PT_MASTHEAD", "   ")
        assert render.masthead() == render.DEFAULT_MASTHEAD


class TestChat:
    def test_header_and_section(self):
        text = render.render_chat(edition(), render.DEFAULT_MASTHEAD)
        assert text.startswith("THE PLOW TIMES \u2014 Sep 11, 2026")
        assert "\u25b8 Weather in Sao Paulo" in text
        assert "Sources: https://example.com/weather" in text

    def test_assignment_tag_and_unsourced(self):
        data = edition(sections=[{
            "kind": "assignment", "topic_id": "t_3f2a", "run_on": "2026-09-11",
            "title": "iPhone 15 price", "body": "$4,299.",
            "sources": ["https://shop.example/x"],
            "tag": "special for this edition",
            "could_not_source": ["the Pro model's price"],
        }])
        text = render.render_chat(data, render.DEFAULT_MASTHEAD)
        assert "special for this edition" in text
        assert "Couldn't source: the Pro model's price" in text

    def test_empty_budget_is_still_an_edition(self):
        text = render.render_chat(edition(sections=[]), render.DEFAULT_MASTHEAD)
        assert "Nothing usable in the budget this time." in text

    def test_sources_deduped(self):
        data = edition(sections=[{
            "kind": "section", "title": "x", "body": "y",
            "sources": ["https://a", "https://a", "https://b"],
        }])
        text = render.render_chat(data, render.DEFAULT_MASTHEAD)
        assert text.count("https://a") == 1

    def test_headline_renders(self):
        # Regression: headline was documented in the SKILL.md example and
        # promised by SOUL.md ("a headline, a short synthesis, and a Sources
        # line") but silently dropped by the renderer -- the model wrote it,
        # nobody ever saw it.
        data = edition(sections=[{
            "kind": "section", "title": "x", "headline": "The real headline",
            "body": "y", "sources": [],
        }])
        text = render.render_chat(data, render.DEFAULT_MASTHEAD)
        assert "The real headline" in text

    def test_missing_headline_is_fine(self):
        text = render.render_chat(edition(), render.DEFAULT_MASTHEAD)
        assert "▸ Weather in Sao Paulo\n  Rain in the afternoon." in text


class TestHtml:
    def test_web_strings_are_escaped(self):
        data = edition(sections=[{
            "kind": "section", "title": "<script>alert(1)</script>",
            "body": "<img onerror=alert(1)>", "sources": ['"><script>'],
        }])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, "<p>{{LEAD}}</p>")
        assert "<script>" not in page
        assert "<img" not in page
        assert "&lt;script&gt;" in page

    def test_placeholders_substituted(self):
        page = render.render_html(edition(), "The Daily", "{{MASTHEAD}}|{{DATE}}|{{LEAD}}")
        assert page.startswith("The Daily|Sep 11, 2026|")
        assert "Weather in Sao Paulo" in page

    def test_headline_renders_escaped(self):
        data = edition(sections=[{
            "kind": "section", "title": "x", "headline": "<b>headline</b>",
            "body": "y", "sources": [],
        }])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, "<p>{{LEAD}}</p>")
        assert 'class="headline"' in page
        assert "<b>headline</b>" not in page
        assert "&lt;b&gt;headline&lt;/b&gt;" in page

    TEMPLATE = "{{PAGE_CLASS}}|{{LEAD}}{{SECTIONS}}|{{WEATHER}}|{{CALENDAR}}|{{MAIL}}|{{SIDEBAR}}"

    def split_slots(self, page):
        return page.split("|", 5)

    def test_news_stays_in_the_news_slot(self):
        data = edition(sections=[
            {"kind": "section", "title": "News", "body": "y", "sources": []},
            {"kind": "section", "title": "Weather", "layout": "sidebar", "body": "z",
             "sources": []},
        ])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, self.TEMPLATE)
        page_class, main_html, weather, calendar, mail, desks = self.split_slots(page)
        assert page_class == "page page--no-desks"
        assert "News" in main_html and "Weather" in main_html
        assert weather == "" and calendar == "" and mail == ""
        assert desks == ""

    def test_no_desks_collapses_the_rail(self):
        page = render.render_html(edition(), render.DEFAULT_MASTHEAD, self.TEMPLATE)
        page_class, _main, weather, calendar, mail, desks = self.split_slots(page)
        assert page_class == "page page--no-desks"
        assert weather == calendar == mail == desks == ""

    def test_weather_desk_has_its_own_slot(self):
        data = edition(sections=[
            {"kind": "section", "title": "Dollar", "desk": "news", "body": "up",
             "sources": []},
            {"kind": "section", "title": "Weather", "desk": "weather", "body": "rain",
             "sources": []},
        ])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, self.TEMPLATE)
        page_class, main_html, weather, calendar, mail, desks = self.split_slots(page)
        assert page_class == "page"
        assert "Dollar" in main_html and "Weather" not in main_html
        assert "Weather" in weather and "section--weather" in weather
        assert "Dollar" not in weather
        assert calendar == "" and mail == ""
        assert "Weather" in desks

    def test_each_desk_is_a_separate_field(self):
        data = edition(sections=[
            {"kind": "section", "title": "News", "desk": "news", "body": "n",
             "sources": []},
            {"kind": "section", "title": "Mail", "desk": "mail", "body": "m",
             "sources": []},
            {"kind": "section", "title": "Weather", "desk": "weather", "body": "w",
             "sources": []},
            {"kind": "section", "title": "Diary", "desk": "calendar", "body": "c",
             "sources": []},
        ])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, self.TEMPLATE)
        _cls, main_html, weather, calendar, mail, _desks = self.split_slots(page)
        assert "News" in main_html
        assert "Weather" in weather and "Diary" not in weather and "Mail" not in weather
        assert "Diary" in calendar and "Weather" not in calendar
        assert "Mail" in mail and "Diary" not in mail
        assert "News" not in weather + calendar + mail

    def test_empty_desk_emits_no_card(self):
        page = render.render_html(edition(), render.DEFAULT_MASTHEAD,
                                  "{{WEATHER}}|{{CALENDAR}}|{{MAIL}}")
        assert page == "||"

    def test_weather_forecast_draws_icons(self):
        data = edition(sections=[{
            "kind": "section", "title": "Weather", "desk": "weather", "body": "rain",
            "forecast": [{"day": "Tue", "date": "17/05", "icon": "rain", "high": 17, "low": 6}],
            "sources": [],
        }])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, "{{WEATHER}}")
        assert 'class="wx-grid"' in page
        assert 'class="wx-icon"' in page
        assert "<img" not in page

    def test_calendar_schedule_draws_kind_icons(self):
        data = edition(sections=[{
            "kind": "section", "title": "Agenda", "desk": "calendar",
            "body": "9am — Product sync.",
            "schedule": [
                {"time": "9am", "title": "Product <sync>", "icon": "meeting"},
                {"time": "11am", "title": "Investor call", "icon": "call"},
            ],
            "sources": ["Calendar.app"],
        }])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, "{{CALENDAR}}")
        assert 'class="cal-list"' in page
        assert page.count('class="cal-icon"') == 2
        assert "Product &lt;sync&gt;" in page
        assert "Product <sync>" not in page
        assert "<img" not in page

    def test_mail_messages_draw_an_envelope(self):
        data = edition(sections=[{
            "kind": "section", "title": "Letters", "desk": "mail",
            "body": "Ana — hello.",
            "messages": [{"sender": "Ana <b>Costa</b>", "subject": "Hello <script>"}],
            "sources": ["Gmail"],
        }])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, "{{MAIL}}")
        assert 'class="mail-list"' in page
        assert 'class="mail-icon"' in page
        assert "Ana &lt;b&gt;Costa&lt;/b&gt;" in page
        assert "Hello &lt;script&gt;" in page
        assert "<script>" not in page
        assert "<img" not in page

    def test_desk_headers_carry_a_drawn_mark(self):
        data = edition(sections=[
            {"kind": "section", "title": "Weather", "desk": "weather", "body": "w",
             "sources": []},
            {"kind": "section", "title": "Agenda", "desk": "calendar", "body": "c",
             "sources": []},
            {"kind": "section", "title": "Letters", "desk": "mail", "body": "m",
             "sources": []},
        ])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, self.TEMPLATE)
        _cls, _news, weather, calendar, mail, _desks = self.split_slots(page)
        assert 'class="desk-icon"' in weather
        assert 'class="desk-icon"' in calendar
        assert 'class="desk-icon"' in mail

    def test_chat_edition_has_no_icons(self):
        data = edition(sections=[{
            "kind": "section", "title": "Agenda", "desk": "calendar",
            "body": "9am — Product sync.",
            "schedule": [{"time": "9am", "title": "Product sync", "icon": "meeting"}],
            "sources": ["Calendar.app"],
        }])
        text = render.render_chat(data, render.DEFAULT_MASTHEAD)
        assert "<svg" not in text
        assert "Product sync" in text

    def test_desks_render_in_newspaper_order(self):
        data = edition(sections=[
            {"kind": "section", "title": "News", "desk": "news", "body": "n",
             "sources": []},
            {"kind": "section", "title": "Mail", "desk": "mail", "body": "m",
             "sources": []},
            {"kind": "section", "title": "Weather", "desk": "weather", "body": "w",
             "sources": []},
            {"kind": "section", "title": "Diary", "desk": "calendar", "body": "c",
             "sources": []},
        ])
        text = render.render_chat(data, render.DEFAULT_MASTHEAD)
        weather_at = text.index("Weather")
        diary_at = text.index("Diary")
        mail_at = text.index("Mail")
        news_at = text.index("News")
        assert weather_at < diary_at < mail_at < news_at

    def test_location_in_header_and_placeholder(self):
        data = edition(location="Sao Paulo")
        text = render.render_chat(data, render.DEFAULT_MASTHEAD)
        assert text.startswith("THE PLOW TIMES \u2014 Sep 11, 2026 \u2014 Sao Paulo")
        page = render.render_html(data, "The Daily", "{{LOCATION}}|{{SECTIONS}}")
        assert page.startswith("Sao Paulo|")

    def test_blank_paragraphs_split(self):
        data = edition(sections=[{
            "kind": "section", "title": "Diary", "desk": "calendar",
            "body": "Today: dentist at 9.\n\nUpcoming: flight on Friday.",
            "sources": ["Calendar.app"],
        }])
        page = render.render_html(data, render.DEFAULT_MASTHEAD, "{{CALENDAR}}")
        assert "Today: dentist at 9." in page
        assert "Upcoming: flight on Friday." in page
        assert "<a href=" not in page

    def test_http_sources_still_link(self):
        page = render.render_html(edition(), render.DEFAULT_MASTHEAD, "{{LEAD}}")
        assert 'href="https://example.com/weather"' in page

    def test_sudoku_is_a_table_not_authored_json(self):
        page = render.render_html(edition(), render.DEFAULT_MASTHEAD, "{{SUDOKU}}")
        assert '<table class="sk-grid">' in page
        assert page.count("<tr>") == 9
        assert "Sudoku" in page
        assert "<div class=\"sk-grid\">" not in page

    def test_sudoku_omits_the_page_rather_than_crash_the_paper(self, monkeypatch):
        def boom(*_args, **_kwargs):
            raise RuntimeError("generator failed")

        monkeypatch.setattr(render.sudoku, "generate_puzzle", boom)
        page = render.render_html(edition(), render.DEFAULT_MASTHEAD, "X{{SUDOKU}}Y")
        assert page == "XY"

    def test_chat_edition_has_no_sudoku_grid(self):
        text = render.render_chat(edition(), render.DEFAULT_MASTHEAD)
        assert "<table" not in text
        assert "sk-grid" not in text


class TestMain:
    def test_prints_chat_to_stdout(self, tmp_path, capsys):
        path = write(tmp_path, edition())
        assert render.main([str(path)]) == 0
        assert "THE PLOW TIMES" in capsys.readouterr().out

    def test_writes_chat_file(self, tmp_path):
        path = write(tmp_path, edition())
        out = tmp_path / "chat.txt"
        render.main([str(path), "--chat", str(out)])
        assert "Weather in Sao Paulo" in out.read_text()

    def test_writes_html(self, tmp_path):
        path = write(tmp_path, edition())
        out = tmp_path / "edition.html"
        render.main([str(path), "--html", str(out)])
        html = out.read_text()
        assert "Weather in Sao Paulo" in html
        assert '<table class="sk-grid">' in html
        assert "Sudoku" in html

    def test_malformed_refused_by_name(self, tmp_path):
        path = write(tmp_path, {"date": "x", "sections": []})
        with pytest.raises(SystemExit, match="invalid edition.json"):
            render.main([str(path)])

    def test_unreadable_refused(self, tmp_path):
        with pytest.raises(SystemExit, match="could not read"):
            render.main([str(tmp_path / "missing.json")])

    def test_deterministic(self, tmp_path):
        path = write(tmp_path, edition())
        first = tmp_path / "a.html"
        second = tmp_path / "b.html"
        render.main([str(path), "--html", str(first)])
        render.main([str(path), "--html", str(second)])
        assert first.read_text() == second.read_text()
