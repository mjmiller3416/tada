"""The two HTML pages the OAuth flow shows: the consent page and the
error page.

They open in a popup from chatgpt.com, often on a phone, so they are
plain server-rendered HTML in Tada's own look (the §5 tokens: amethyst
for "go", warm cream background, rounded cards, Nunito) with no scripts.
Every dynamic value goes through html.escape.
"""

from html import escape

_STYLE = """
:root {
  --purple: #8354c9; --purple-strong: #6c3fac; --purple-soft: #f1e8fb;
  --bg: #fcf5f0; --surface: #ffffff; --ink: #3a2823; --ink-soft: #8c7268;
  --line: #f1e2d9; --coral: #c14840; --coral-soft: #fbe4e1;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--ink); }
body {
  font-family: "Nunito", ui-rounded, "Segoe UI", system-ui, sans-serif;
  font-weight: 500; line-height: 1.45; min-height: 100vh;
  display: flex; align-items: flex-start; justify-content: center;
  padding: 32px 16px;
}
.card {
  width: 100%; max-width: 420px; background: var(--surface);
  border-radius: 12px; padding: 24px 20px;
  box-shadow: 0 2px 12px rgba(58, 40, 35, 0.08);
}
.brand { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.logo {
  width: 40px; height: 40px; border-radius: 12px; background: var(--purple-soft);
  display: grid; place-items: center; font-size: 22px;
}
.brand span { font-weight: 800; font-size: 20px; }
h1 { font-size: 22px; font-weight: 800; margin: 0 0 8px; }
p { margin: 0 0 12px; }
.soft { color: var(--ink-soft); font-size: 15px; }
.who {
  background: var(--purple-soft); border-radius: 12px; padding: 10px 14px;
  margin: 12px 0 16px; font-weight: 800;
}
label { display: block; font-weight: 800; margin: 12px 0 6px; }
input[type=password] {
  width: 100%; font: inherit; font-size: 20px; letter-spacing: 4px;
  padding: 12px 14px; border: 2px solid var(--line); border-radius: 14px;
  background: var(--surface); color: var(--ink);
}
input[type=password]:focus { outline: none; border-color: var(--purple); }
.error {
  background: var(--coral-soft); color: var(--coral); border-radius: 12px;
  padding: 10px 14px; margin: 0 0 12px; font-weight: 800;
}
.buttons { display: flex; flex-direction: column; gap: 10px; margin-top: 20px; }
button {
  font: inherit; font-weight: 800; font-size: 17px; border: 0; cursor: pointer;
  border-radius: 14px; padding: 14px 16px; min-height: 52px; width: 100%;
}
.allow { background: var(--purple); color: #fff; }
.allow:hover { background: var(--purple-strong); }
.cancel { background: transparent; color: var(--ink-soft); }
details { margin-top: 8px; }
summary { cursor: pointer; color: var(--ink-soft); font-size: 15px; }
"""


def _shell(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<meta name=\"referrer\" content=\"no-referrer\">"
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main class=\"card\"><div class=\"brand\"><div class=\"logo\">🎉</div>"
        f"<span>Tada</span></div>{body}</main></body></html>"
    )


def consent_page(
    *,
    hidden: dict[str, str],
    user_name: str | None,
    error: str | None = None,
) -> str:
    """The "ChatGPT wants to use Tada as you" page. With an existing Tada
    session it names the member and asks only for Allow; without one it
    asks for the member's Tada PIN on the same page. `hidden` carries the
    authorization request and the CSRF token back on the POST."""
    fields = "".join(
        f'<input type="hidden" name="{escape(k)}" value="{escape(v)}">'
        for k, v in hidden.items()
    )
    error_html = f'<p class="error" role="alert">{escape(error)}</p>' if error else ""
    pin_input = (
        '<input type="password" id="pin" name="pin" inputmode="numeric" '
        'pattern="[0-9]*" autocomplete="current-password" maxlength="12">'
    )
    if user_name:
        first = user_name.split()[0]
        who = (
            f'<p class="who">Signed in as {escape(user_name)}</p>'
            "<details><summary>Not you? Use your own PIN</summary>"
            f'<label for="pin">Your Tada PIN</label>{pin_input}</details>'
        )
        lead = f"ChatGPT wants to use Tada as you, {escape(first)}."
    else:
        who = f'<label for="pin">Your Tada PIN</label>{pin_input}'
        lead = "ChatGPT wants to use Tada as you."
    body = (
        "<h1>Connect ChatGPT?</h1>"
        f"<p>{lead} It will be able to see and change everything you can.</p>"
        '<p class="soft">You can disconnect it any time from Tada’s Settings.</p>'
        f"{error_html}"
        f'<form method="post" action="/api/oauth/authorize">{fields}{who}'
        '<div class="buttons">'
        '<button class="allow" type="submit" name="action" value="allow">Allow</button>'
        '<button class="cancel" type="submit" name="action" value="cancel" '
        'formnovalidate>Cancel</button>'
        "</div></form>"
    )
    return _shell("Connect ChatGPT to Tada", body)


def error_page(message: str) -> str:
    """Shown instead of redirecting when the request can't be trusted
    (unknown client, unregistered redirect URI, expired form)."""
    body = (
        "<h1>That didn’t work</h1>"
        f"<p>{escape(message)}</p>"
        '<p class="soft">Close this window and try connecting again from ChatGPT.</p>'
    )
    return _shell("Tada sign-in", body)
