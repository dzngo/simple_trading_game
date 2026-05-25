# Project Notes

## Verification Rule

Do not use Browser to visually review or verify the app unless the user explicitly asks for Browser-based verification.

Default verification should use code inspection, compile checks, command-line smoke tests, and direct database checks.

## UI Design Rule

Prefer compact layouts. Display related controls and data by rows or columns depending on context, with the goal of reducing vertical sprawl while keeping the workflow readable.

## Streamlit State Rule

Avoid mixing an external button with widgets inside a `st.form` when the button mutates the same widget state used by the form submission.

Observed bug:
- On the Bank page, `Use market price` was outside the form.
- `Agreed price` and `Submit declaration` were inside the form.
- The displayed price changed to the latest Market Price, but the form submitted an older stale value.

Rule:
- If a quick-fill button updates a value that will be submitted, keep the input and submit flow outside `st.form`, or put all related controls inside the same form.
- On submit, read the final value from `st.session_state` or from the same immediate widget state that the quick-fill button updates.

Current Bank page pattern:
- `Use market price` writes to `st.session_state["bank_agreed_price"]`.
- `Agreed price` uses the same key.
- `Submit declaration` reads `st.session_state["bank_agreed_price"]`.
