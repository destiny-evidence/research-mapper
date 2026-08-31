from gen import *

Q = "Draft search queries"; SQ = "Search by query"; CT = "Choose taxonomy concepts"
SC = "Search by concept"; CR = "Set screening criteria"; SE = "Screen the evidence"
MD = "Choose map dimensions"; MS = "Fill in subtopics"; PM = "Place evidence on the map"

def chip(t, gone=False):
    if gone:
        return (f'<div class="m" style="font-size: 10.5px; color: #b8b4ac; background: #f0eee9; '
                f'padding: 4px 8px; text-decoration: line-through;">{t}</div>')
    return f'<div class="m" style="font-size: 10.5px; color: #4a4843; background: #ebe8e2; padding: 4px 8px;">{t}</div>'

QUERIES = ('<div style="display: flex; flex-wrap: wrap; gap: 5px;">'
    + chip("hesitanc* AND (uptake OR coverage) AND HPV")
    + chip('cost AND barrier* AND vaccin* AND (LMIC OR "low-income")')
    + chip('"parental refusal" AND HPV')
    + chip('(distance OR "travel time") AND vaccin* AND adolescen*')
    + chip("HPV vaccine", True) + chip("adolescent health", True) + '</div>'
    + said("Barriers get phrased several ways here: hesitancy, refusal, cost, distance. One search per family. "
           "A single broad query returns coverage papers that never discuss barriers."))

def counts(pairs):
    out = []
    for label, value, bad in pairs:
        c = "#9c3a2f" if bad else "#2b2a27"
        lc = "#b57a72" if bad else "#a09c94"
        out.append(f'<div><div class="lab" style="color: {lc};">{label}</div>'
                   f'<div class="m" style="font-size: 16px; color: {c}; margin-top: 2px;">{value}</div></div>')
    return '<div style="display: flex; gap: 28px; margin-top: 14px;">' + "".join(out) + '</div>'

SCREENING = ('<div style="height: 4px; background: #e6e3dc; max-width: 560px; overflow: hidden;">'
             '<div style="width: 62%; height: 4px; background: #2b2a27;"></div></div>'
             + counts([("Included", "62", False), ("Excluded", "267", False), ("Failed", "2", True)]))

# ---- Running -------------------------------------------------------------
open("Main.dc.html", "w").write(screen(
    header("HPV &middot; started 14:02 &middot; running 12m"),
    [row("done", Q, "kept 4 of 6", body=QUERIES),
     row("done", SQ, "412 references"),
     row("done", CT, "2 groups &middot; 6 concepts"),
     row("done", SC, "118 new references"),
     row("done", CR, "kept 4 of 5, added 1"),
     row("running", SE, "331 of 530", body=SCREENING),
     row("todo", MD, "will ask you"),
     row("todo", MS, "will ask you"),
     row("todo", PM)],
    880))

# ---- Failed --------------------------------------------------------------
FAIL = ('<div class="m" style="font-size: 11.5px; color: #9c3a2f; background: #fbf1ef; border: 1px solid #e8d2ce; '
        'padding: 9px 11px; max-width: 620px; line-height: 1.5;">TaxonomySearchError: vocabulary fetch returned 503'
        '<br>vocab.evidence-repository.org &middot; 14:31:08</div>'
        '<div style="margin-top: 13px;"><div style="font-size: 12.5px; color: #f4f3f0; background: #2b2a27; '
        'padding: 8px 18px; font-weight: 500; display: inline-block;">Retry</div></div>')
open("Failed.dc.html", "w").write(screen(
    header("HPV &middot; started 14:02 &middot; stopped 14:31"),
    [row("done", Q, "kept 4 of 6"),
     row("done", SQ, "412 references"),
     row("failed", CT, "failed after 2 attempts", body=FAIL, accent="#9c3a2f", width=169),
     row("todo", SC), row("todo", CR), row("todo", SE),
     row("todo", MD), row("todo", MS), row("todo", PM)],
    760))
print("Main, Failed")

# ---- Ask: the agent's own question --------------------------------------
def option(text, on, note=""):
    box = ('<div style="width: 14px; height: 14px; background: #a8551a; display: grid; place-items: center; flex-shrink: 0;">'
           '<svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="#ffffff" stroke-width="2.2" '
           'stroke-linecap="round" stroke-linejoin="round"><path d="M2 6.4 L4.6 9 L10 3"></path></svg></div>'
           if on else '<div style="width: 14px; height: 14px; border: 1px solid #b3b0a9; background: #ffffff; flex-shrink: 0;"></div>')
    bg = "background: #faf8f4;" if on else ""
    return (f'<div style="display: flex; gap: 11px; align-items: center; padding: 10px; '
            f'border-bottom: 1px solid #e9e6e0; {bg}">{box}'
            f'<div style="font-size: 13px; color: #2b2a27;">{text}</div>{note}</div>')

def trace(idx, call, colour="#4a4843"):
    """A finished iteration: one line, the call is its identity."""
    return ('<div style="display: flex; align-items: center; gap: 12px; padding: 8px 0; '
            'border-bottom: 1px solid #eeebe5;">'
            f'<div class="m" style="font-size: 10.5px; color: #c4c0b8; width: 14px; flex-shrink: 0;">{idx}</div>'
            f'<div class="m" style="font-size: 11px; color: {colour}; flex-grow: 1;">{call}</div>'
            f'{toggle(False)}</div>')

def pending(idx, thought, call, obs):
    return ('<div style="margin: 0 -8px; padding: 11px 8px; border: 1px dashed #a8551a; background: #fdfaf5; '
            'display: flex; gap: 12px;">'
            f'<div class="m" style="font-size: 10.5px; color: #a8551a; width: 14px; flex-shrink: 0; padding-top: 2px;">{idx}</div>'
            f'<div style="flex-grow: 1;">{said(thought, top=0)}'
            f'<div class="m" style="font-size: 11px; color: #4a4843; margin-top: 7px;">{call}</div>'
            f'<div class="m" style="font-size: 10.5px; color: #a8551a; margin-top: 3px;">{obs}</div></div>'
            f'{toggle(True)}</div>')

TRACE = "".join([
    trace(0, "list_schemes()"),
    trace(1, "list_concepts_in_scheme(scheme=&quot;hpv-barriers&quot;)"),
    trace(2, "get_narrower(local_ref=&quot;b12&quot;)"),
    trace(3, "lookup_concepts(label=&quot;cost&quot;)"),
    trace(4, "lookup_concepts(label=&quot;equity&quot;) &mdash; no concepts found", "#9c3a2f"),
    trace(5, "get_concept_detail(local_ref=&quot;d07&quot;)"),
    pending(6,
            "Equitable Access sits under delivery, not barriers, so the two readings pick different concepts.",
            "ask_for_clarification(request={&quot;question&quot;: &quot;Barriers to what, exactly?&quot;, &hellip;})",
            "waiting"),
])

ASK = ('<div style="font-size: 15px; color: #2b2a27; font-weight: 500; max-width: 640px; line-height: 1.45;">'
       'Barriers to what, exactly? The two readings pick out different concepts.</div>'
       '<div style="margin-top: 14px; border-top: 1px solid #e9e6e0;">'
       + option("Barriers families face when deciding", True)
       + option("Barriers in how the vaccine is delivered", True)
       + option("Both, kept apart on the map", False)
       + option("None of these", False) + option("I&#39;m not sure", False)
       + '</div>'
       '<div style="margin-top: 15px;"><div style="font-size: 12.5px; color: #f4f3f0; background: #2b2a27; '
       'padding: 8px 20px; font-weight: 500; display: inline-block;">Answer</div></div>'
       '<div style="margin-top: 20px; border-top: 1px solid #d6d2ca;">'
       '<div style="display: flex; align-items: center; gap: 11px; padding: 10px 0;">'
       + toggle(True) +
       '<div style="font-size: 12.5px; color: #4a4843;">How it got here</div>'
       '<div class="m" style="font-size: 11px; color: #a09c94;">7 steps</div></div>'
       f'<div style="padding-bottom: 4px;">{TRACE}</div></div>')

open("AskSelect.dc.html", "w").write(screen(
    header("HPV &middot; started 14:02 &middot; waiting"),
    [row("done", Q, "kept 4 of 6"),
     row("done", SQ, "412 references"),
     row("ask", CT, "it has a question for you", body=ASK, accent="#a8551a", width=169),
     row("todo", SC), row("todo", CR), row("todo", SE),
     row("todo", MD, "will ask you"), row("todo", MS, "will ask you"), row("todo", PM)],
    1180))
print("AskSelect")

# ---- Ask: three at once --------------------------------------------------
def tag(t):
    return f'<div style="font-size: 11.5px; color: #6f6b63; background: #e6e3dc; padding: 4px 9px;">{t}</div>'
def editable(t):
    return (f'<div style="display: flex; align-items: center; gap: 7px; font-size: 11.5px; color: #2b2a27; '
            f'border: 1px solid #d6d2ca; background: #ffffff; padding: 4px 7px 4px 9px;">{t}'
            '<svg width="8" height="8" viewBox="0 0 12 12" fill="none" stroke="#a09c94" stroke-width="1.8" '
            'stroke-linecap="round"><path d="M3 3 L9 9 M9 3 L3 9"></path></svg></div>')
ADD = ('<div style="display: flex; align-items: center; gap: 5px; font-size: 11.5px; color: #86837c; '
       'border: 1px dashed #cfcbc3; padding: 4px 10px;"><svg width="9" height="9" viewBox="0 0 12 12" fill="none" '
       'stroke="#86837c" stroke-width="1.6" stroke-linecap="round"><path d="M6 2.5 L6 9.5 M2.5 6 L9.5 6"></path></svg>add</div>')

def sub(name, chips, saved):
    box = ('<div style="width: 14px; height: 14px; background: #5f7d69; display: grid; place-items: center; flex-shrink: 0;">'
           '<svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="#ffffff" stroke-width="2.2" '
           'stroke-linecap="round" stroke-linejoin="round"><path d="M2 6.4 L4.6 9 L10 3"></path></svg></div>'
           if saved else '<div style="width: 14px; height: 14px; border: 1px solid #b3b0a9; background: #ffffff; flex-shrink: 0;"></div>')
    tail = ('<div class="lab" style="color: #5f7d69;">saved</div>' if saved else "")
    action = "" if saved else ('<div style="margin-top: 11px; padding-left: 22px;">'
        '<div style="font-size: 12px; color: #2b2a27; border: 1px solid #b3b0a9; padding: 6px 14px; '
        'background: #ffffff; display: inline-block;">Save</div></div>')
    bg = "background: #f7f6f2;" if saved else ""
    return (f'<div style="padding: 13px 10px; border-bottom: 1px solid #e9e6e0; {bg}">'
            f'<div style="display: flex; align-items: center; gap: 8px;">{box}'
            f'<div style="font-size: 13px; color: #2b2a27; font-weight: 500;">{name}</div>{tail}</div>'
            f'<div style="display: flex; flex-wrap: wrap; gap: 5px; margin-top: 9px; padding-left: 22px;">{chips}</div>'
            f'{action}</div>')

EDIT = ('<div style="font-size: 15px; color: #2b2a27; font-weight: 500; max-width: 640px; line-height: 1.45;">'
        'Check the groupings for each dimension</div>'
        + said("Three dimensions that cut across each other rather than overlap. Study design is the weak one: "
               "31 of 94 qualitative, the rest spread thin.")
        + '<div style="margin-top: 14px; border-top: 1px solid #e9e6e0;">'
        + sub("Barrier", "".join(tag(t) for t in
              ["Cost and access", "Vaccine hesitancy", "Parental refusal", "Health-system capacity", "Misinformation"]), True)
        + sub("Where the vaccine is given",
              "".join(editable(t) for t in ["School-based", "Health facility", "Community outreach"]) + ADD, False)
        + sub("How the study was done",
              "".join(editable(t) for t in ["Trial", "Cohort", "Qualitative"])
              + '<div style="border: 1.5px solid #2b2a27; background: #ffffff; padding: 4px 9px; font-size: 11.5px; '
                'color: #2b2a27;">Mixed methods<span style="color: #b8b4ac;">|</span></div>', False)
        + '</div><div style="display: flex; align-items: center; gap: 12px; margin-top: 15px;">'
        '<div style="font-size: 12.5px; color: #b8b4ac; background: #eae7e1; padding: 8px 20px;">Continue</div>'
        '<div style="font-size: 11.5px; color: #a09c94;">1 of 3 saved</div></div>')

open("AskEditList.dc.html", "w").write(screen(
    header("HPV &middot; started 14:02 &middot; waiting"),
    [row("done", SE, "94 included &middot; 433 excluded &middot; 3 failed"),
     row("done", MD, "3 dimensions"),
     row("ask", MS, "3 questions", body=EDIT, accent="#a8551a", width=169),
     row("todo", PM)],
    920))
print("AskEditList")

# ---- The map -------------------------------------------------------------
def bubble(n):
    d = round(13.9 * (n ** 0.5))
    fs = 13 if d >= 46 else (12 if d >= 40 else (11.5 if d >= 34 else 10.5))
    return (f'<div class="m" style="width: {d}px; height: {d}px; border-radius: 50%; background: #3d3b36; '
            f'color: #f4f3f0; display: grid; place-items: center; font-size: {fs}px;">{n}</div>')
EMPTY = '<div style="width: 9px; height: 9px; border-radius: 50%; border: 1px solid #cfcbc3;"></div>'

ROWS = [("Cost and access", [9, 14, 4]), ("Vaccine hesitancy", [12, 7, 0]),
        ("Parental refusal", [11, 4, 0]), ("Health-system capacity", [0, 0, 0]),
        ("Misinformation", [0, 0, 0])]
COLS = ["School-based", "Health facility", "Community outreach"]

def grid():
    out = ['<div style="border-right: 1px solid #e6e3dc; border-bottom: 1px solid #d6d2ca;"></div>']
    for i, c in enumerate(COLS):
        edge = "#d6d2ca" if i == 2 else "#e6e3dc"
        out.append(f'<div class="lab" style="border-right: 1px solid {edge}; border-bottom: 1px solid #d6d2ca; '
                   f'padding: 9px 12px; color: #6f6b63;">{c}</div>')
    for r, (name, vals) in enumerate(ROWS):
        last = r == len(ROWS) - 1
        hedge = "#d6d2ca" if last else "#e6e3dc"
        dim = "#86837c" if not any(vals) else "#2b2a27"
        out.append(f'<div style="border-right: 1px solid #e6e3dc; border-bottom: 1px solid {hedge}; padding: 0 12px; '
                   f'display: flex; align-items: center;"><div style="font-size: 12.5px; color: {dim};">{name}</div></div>')
        for i, v in enumerate(vals):
            edge = "#d6d2ca" if i == 2 else "#e6e3dc"
            bg = " background: #faf9f6;" if not any(vals) else ""
            out.append(f'<div style="border-right: 1px solid {edge}; border-bottom: 1px solid {hedge}; height: 70px; '
                       f'display: grid; place-items: center;{bg}">{bubble(v) if v else EMPTY}</div>')
    return ('<div style="border-top: 1px solid #d6d2ca; border-left: 1px solid #d6d2ca; background: #ffffff; margin-top: 12px;">'
            '<div style="display: grid; grid-template-columns: 200px repeat(3, minmax(0, 1fr));">'
            + "".join(out) + '</div></div>')

def facet(active, label):
    if active:
        return f'<div style="font-size: 11.5px; color: #f4f3f0; background: #2b2a27; padding: 5px 10px;">{label}</div>'
    return (f'<div style="font-size: 11.5px; color: #4a4843; border: 1px solid #d6d2ca; padding: 5px 10px; '
            f'background: #ffffff;">{label}</div>')

MAP = ('<div style="display: flex; align-items: flex-end; gap: 20px;"><div style="flex-grow: 1;">'
       '<div style="font-size: 14px; color: #2b2a27; font-weight: 600;">Barrier by where the vaccine is given</div>'
       '<div style="font-size: 12px; color: #86837c; margin-top: 5px;">61 of 94 included references placed. '
       '33 could not be placed.</div></div>'
       '<div style="display: flex; gap: 4px; flex-shrink: 0;">'
       + facet(True, "All 61") + facet(False, "Trial 14") + facet(False, "Cohort 18")
       + facet(False, "Qualitative 29") + '</div></div>' + grid()
       + '<div style="font-size: 11.5px; color: #86837c; margin-top: 13px; max-width: 560px; line-height: 1.5;">'
         'An empty circle means nothing was placed there, not that nothing exists.</div>')

def page(head_meta, workflow_block, height):
    return (HEAD + f'<div style="width: 1180px; height: {height}px; display: flex; flex-direction: column; '
            'overflow: hidden; background: #f4f3f0;">\n' + CHROME +
            '  <div style="flex-grow: 1; overflow: hidden; padding: 0 80px;">\n'
            '    <div style="max-width: 1020px; display: flex; flex-direction: column;">\n'
            '<div style="padding: 22px 0 15px 0; display: flex; align-items: flex-start; gap: 24px;">'
            '<div style="flex-grow: 1;">'
            f'<div style="font-size: 17px; line-height: 1.4; color: #2b2a27; font-weight: 500; max-width: 640px;">{QUESTION}</div>'
            f'<div class="m" style="font-size: 11px; color: #a09c94; margin-top: 8px;">{head_meta}</div></div>'
            + RECORD + '</div>'
            + workflow_block + MAP +
            '    </div>\n  </div>\n</div>\n</x-dc>\n</body>\n</html>\n')

BAR_SUMMARY = "9 steps &middot; you answered 5 questions &middot; 3 references failed"
COLLAPSED = ('<div style="display: flex; align-items: center; gap: 13px; padding: 10px 14px; background: #ffffff; '
             f'border: 1px solid #d6d2ca; margin-bottom: 24px;">{PIP["done"]}'
             '<div style="font-size: 13px; color: #2b2a27; font-weight: 500;">Workflow</div>'
             f'<div style="font-size: 12.5px; color: #86837c; flex-grow: 1;">{BAR_SUMMARY}</div>'
             f'{toggle(False)}</div>')
open("Complete.dc.html", "w").write(page("HPV &middot; 14:02 to 15:07", COLLAPSED, 880))

INNER = "".join([
    row("done", Q, "kept 4 of 6"), row("done", SQ, "412 references"),
    row("done", CT, "2 groups &middot; 6 concepts",
        body='<div style="display: flex; flex-wrap: wrap; gap: 5px;">'
             + tag("Vaccine Hesitancy") + tag("Parental Refusal") + tag("Out-of-pocket Cost")
             + tag("School-based Delivery") + tag("Health Facility Delivery") + tag("Community Outreach")
             + '</div>' + said("Groups are AND&#39;d across schemes and OR&#39;d within one. Nothing in this "
                               "vocabulary expresses equity, so the map cannot split on it.")),
    row("done", SC, "118 new references"), row("done", CR, "kept 4 of 5, added 1"),
    row("done", SE, "94 included &middot; 433 excluded &middot; 3 failed"),
    row("done", MD, "3 dimensions"), row("done", MS, "3 questions"),
    row("done", PM, "61 of 94 placed")])
OPEN_BAR = ('<div style="background: #ffffff; border: 1px solid #d6d2ca; margin-bottom: 22px;">'
            '<div style="display: flex; align-items: center; gap: 13px; padding: 10px 14px; '
            f'border-bottom: 1px solid #d6d2ca; background: #f7f6f2;">{PIP["done"]}'
            '<div style="font-size: 13px; color: #2b2a27; font-weight: 500;">Workflow</div>'
            f'<div style="font-size: 12.5px; color: #86837c; flex-grow: 1;">{BAR_SUMMARY}</div>{toggle(True)}</div>'
            f'<div style="padding: 2px 14px 8px 14px;">{INNER}</div></div>')
open("Reopened.dc.html", "w").write(page("HPV &middot; 14:02 to 15:07", OPEN_BAR, 1420))
print("Complete, Reopened")

# ---- Sessions ------------------------------------------------------------
SESSIONS = [
    ("ask", "What barriers reduce HPV vaccination uptake among adolescent girls in low- and middle-income countries?", "HPV", "needs you", "31 Aug"),
    ("running", "Which school feeding programmes improve attendance in East Africa?", "ESEA", "", "31 Aug"),
    ("done", "What evidence exists on HPV catch-up campaigns for out-of-school girls?", "HPV", "", "28 Aug"),
    ("failed", "Do SMS reminders improve second-dose completion?", "HPV", "failed", "30 Aug"),
]
def session_row(state, q, community, note, when):
    colour = {"ask": "#a8551a", "failed": "#9c3a2f"}.get(state, "#2b2a27")
    tail = (f'<div style="font-size: 12px; color: {colour}; flex-shrink: 0;">{note}</div>' if note else "")
    return ('<div style="display: flex; align-items: center; gap: 14px; padding: 14px 0; '
            f'border-bottom: 1px solid #e0ddd6;">{PIP[state]}'
            f'<div style="font-size: 13.5px; color: #2b2a27; line-height: 1.4; flex-grow: 1; max-width: 640px;">{q}</div>'
            f'{tail}<div class="m" style="font-size: 10.5px; color: #86837c; border: 1px solid #ddd9d2; '
            f'padding: 2px 6px; flex-shrink: 0;">{community}</div>'
            f'<div class="m" style="font-size: 11px; color: #a09c94; width: 48px; text-align: right; flex-shrink: 0;">{when}</div></div>')

open("Entry.dc.html", "w").write(
    HEAD + '<div style="width: 1180px; height: 560px; display: flex; flex-direction: column; overflow: hidden; '
    'background: #f4f3f0;">\n' + CHROME +
    '  <div style="flex-grow: 1; overflow: hidden; padding: 0 80px;">\n'
    '    <div style="max-width: 1020px; display: flex; flex-direction: column;">\n'
    '<div style="padding: 24px 0 14px 0; display: flex; align-items: center; gap: 20px; border-bottom: 1px solid #d6d2ca;">'
    '<div style="font-size: 16px; color: #2b2a27; font-weight: 500;">Sessions</div><div style="flex-grow: 1;"></div>'
    '<div style="font-size: 12px; color: #f4f3f0; background: #2b2a27; padding: 8px 16px; font-weight: 500;">'
    'Ask a new question</div></div>'
    + "".join(session_row(*s) for s in SESSIONS)
    + '    </div>\n  </div>\n</div>\n</x-dc>\n</body>\n</html>\n')
print("Entry")
