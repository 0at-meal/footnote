# Interview script: credit / leveraged-finance analysts (P0-11)

**Length:** 40 minutes. **Goal:** learn how this person *actually* handles EBITDA
add-backs today and whether they would pay to stop doing it. The goal is not to sell
Footnote.

Ground rules for the interviewer:
- **Ask about the past, not the future.** "Walk me through the last time…" beats "Would
  you use…?". Opinions about hypothetical products are weak evidence; past behaviour and
  money already spent are strong evidence.
- **Don't pitch until §6.** If they ask what you're building, say: "I'll show you at the
  end. First I want to understand how you do it today."
- **Dig into specifics.** Ask for an example, a number, a tool name, a time spent. "How
  long did that take?" "What happened next?" "Can you show me?"
- **Silence is fine.** Let them fill it.
- **Write down exact words for key answers** (marked ★). The scoresheet needs quotes.
- Question IDs (W1, P2, …) map to the [scoring rubric](scoring-rubric.md).

---

## 0. Opening (2 min)

> Thanks for making time. I'm researching how credit analysts work with the EBITDA numbers
> issuers report, especially the adjustments. I'm not selling anything today. There are no
> right answers; "we don't do that" is a useful answer. Is it OK if I take notes? I won't
> attribute anything to you or your firm.

Record the consent in the notes.

## 1. Role and context (5 min)

- **R1.** What's your role, and what kind of credit do you cover? (Direct lending, BDC,
  HY, loans, CLO, bank leveraged finance…)
- **R2.** Roughly how many issuers or credits are you responsible for? How many are public
  filers with SEC reports?
- **R3.** Who else on your team touches the same numbers? (Analysts, PM, portfolio
  monitoring, risk.)

## 2. Workflow: the last time (10 min)

- **W1 ★.** Think of the last earnings season. Walk me through what you did with one
  issuer's release, from the moment it came out.
- **W2 ★.** Where did the Adjusted EBITDA number you used come from? Did you take the
  issuer's figure, adjust it, or rebuild it from the bridge? *(Probe: which add-backs did
  you change, and why?)*
- **W3 ★.** How often do you rebuild or adjust an issuer's EBITDA bridge yourself: every
  quarter, at underwriting only, or ad hoc? For how many issuers?
- **W4.** Where does that work live? (Excel model, internal system, vendor screen, credit
  memo.) Can you describe the sheet: columns, rows, sources?
- **W5.** How do you compare against the credit agreement's definition of EBITDA
  (covenant EBITDA), if at all?

## 3. Pain (7 min)

- **P1 ★.** What's the most annoying or time-consuming part of that? How long does it take
  per issuer per quarter?
- **P2 ★.** Tell me about a time an add-back or definition change caught you out (a
  restated prior period, a renamed line, a new "non-recurring" item that keeps recurring).
  What happened? What did it cost?
- **P3.** How do you notice when an issuer changes how it defines Adjusted EBITDA?
- **P4.** If this work disappeared tomorrow, what would you do with the time? *(Gauges
  importance; don't lead.)*

## 4. Trust in normalization (6 min)

- **T1 ★.** If someone else normalized EBITDA for you (decided which add-backs to accept
  or reverse), what would you need to see before you used their number? *(Probe: source
  links, itemized adjustments, the ability to override, the methodology document.)*
- **T2.** Which add-backs do you *always* reverse? Which do you always accept? Which
  depend? *(SBC, restructuring, synergies, "other". Do not suggest answers before they
  give theirs.)*
- **T3.** Would one standard normalization be useful, or does every firm or analyst need its
  own policy? Does your firm have a written add-back policy?
- **T4.** May I send you a 2-page draft of a normalization method to critique? *(If yes, they
  are a P0-14 reviewer candidate. Mark it on the tracker.)*

## 5. Existing tools and spend (5 min)

- **E1 ★.** What tools or data do you use for this today? (Bloomberg, CapIQ, FactSet,
  Daloopa, Calcbench, Moody's/S&P, 9fin, Octus/Reorg, Covenant Review, in-house…) For
  what exactly?
- **E2 ★.** Does any of them already give you normalized EBITDA *and* tell you when an
  issuer's definition or prior numbers change? *(Exact words. This is criterion C.)*
- **E3.** What do you pay, or what does your team pay, for those, roughly? Who decided to
  buy them?

## 6. Price and buying process (4 min)

Now describe Footnote in two sentences, no more:

> A record of every US issuer's EBITDA bridge, each line mapped to a standard add-back
> category and linked to the exact sec.gov text, with alerts when an issuer changes its
> definition or restates a prior quarter. Normalized EBITDA is computed under a published
> policy that you can override.

- **B1 ★.** Is that something your team would pay for? What would it have to replace or
  beat?
- **B2 ★.** What would you expect something like that to cost per seat or per team per
  year? What do comparable tools cost you? *(Any number they give is a price anchor:
  record it exactly.)*
- **B3.** Who besides you would have to agree to a purchase? What's the process (trial,
  security review, procurement)? How long does it usually take?
- **B4 ★.** Would you want to try an early version on issuers you cover? *(A clear yes, or
  their own request for a trial, counts for criterion B.)*

## 7. Close (2 min)

- **C1.** Is there anything I should have asked but didn't?
- **C2.** Who else should I talk to: a colleague, or someone at another fund? Could you
  introduce us?
- **C3.** May I follow up with the summary of findings, and with the draft method if you
  agreed in T4?

Thank them. Within 24 hours, fill in the [scoresheet](templates/scoresheet.md) and update the
[tracker](tracker.md).
