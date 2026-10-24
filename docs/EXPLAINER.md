# Footnote, explained from the beginning

> **Who this is for.** You do not need to know about finance or software. Read the units in
> order. Each unit uses only ideas from the units before it.
>
> **How to read it.** Each unit starts with a real-world example and then gives the general
> rule. Each unit ends with a short box called *Remember*. If you can explain the box in your
> own words, go to the next unit.
>
> **About the numbers.** The company "Example Co." and its numbers are invented to teach. They
> are not real data. The numbers about Footnote's own progress (Unit 6) are real and come
> from [eval/RESULTS.md](../eval/RESULTS.md).

---

## Unit 0. The foundations

This unit gives you the ten ideas you need before we talk about Footnote. Read them in order.

### 0.1 Profit

A lemonade stand sells $100 of lemonade in one week. Lemons, sugar and cups cost $70. The
stand made **$30 of profit**.

**Rule:** profit is the money that comes in minus the money that goes out.

Large companies calculate profit in the same way, but they have thousands of kinds of costs.

### 0.2 Public companies

Some companies sell small pieces of themselves to anyone who wants to buy one. These pieces
are called *shares*. A company that does this is a **public company**.

Many people put their savings into public companies. For this reason, US law makes public
companies tell everyone how much money they make and spend.

### 0.3 The SEC and its website

The **SEC** is the US government office that controls this. Each public company must send its
results to the SEC. The SEC puts the results on a free public website, `sec.gov`. Anyone can
read them.

The website is very large. It has millions of documents from thousands of companies.

### 0.4 The quarterly announcement

A company sends results to the SEC every three months. A three-month period is a **quarter**,
so there are four quarters in a year.

Each quarter, most companies also publish a short **announcement** of their results, like a
news article. They attach it to a small official form. Footnote reads these announcements.

**Important:** the announcement is written for people to read. It is not neatly organized for
a computer. Every company lays out its tables in its own way.

### 0.5 Official profit and "friendlier" profit

The law sets strict rules for how a company calculates its official profit. Every company must
follow the same rules. In this document we call the result **official profit**.

Companies also like to show their own, friendlier version of profit. They say: "Our official
profit was low because of some unusual costs. Here is what our profit looks like without
them."

### 0.6 EBITDA

The friendlier number that matters most for Footnote has a long name: **EBITDA** (say
"EE-bit-dah").

EBITDA starts from official profit and puts back four kinds of cost:

1. the cost of borrowed money (interest);
2. taxes;
3. the slow wearing-out of buildings and machines;
4. the slow using-up of things you cannot touch, such as a patent.

**Why people use it:** it shows roughly how much money the main business makes, before loan
payments and taxes. It is easier to compare companies this way.

**Worked example (invented).** Example Co. has an official profit of 50. It paid 30 in
interest and 15 in taxes. Its machines and patents wore out or were used up by 40.

- EBITDA = 50 + 30 + 15 + 40 = **135**.

Each item is a real cost that the company did pay. EBITDA only puts these costs to one side.

### 0.7 Adjusted EBITDA and add-backs

Most companies go one step further. They also put back costs that they call "one-off," for
example:

- a lawsuit they had to pay;
- the cost of closing a factory and letting staff go;
- the cost of buying another company.

The result is **Adjusted EBITDA**. Each cost that the company puts back is an **add-back**.

**A school example.** A student scores 60 on a set of tests. The student says: "Ignore the test
I took when I was sick. Without it, my score is 75." The 75 is like Adjusted EBITDA. The
sick-day test is like an add-back. The question is always: *was it really a one-off?*

### 0.8 The bridge

A company does not only show the final friendly number. It also shows a small table that
walks, line by line, from official profit to Adjusted EBITDA. This table is called the
**bridge**.

**Worked example: the bridge of Example Co. (invented), in millions of dollars**

| Line | Amount |
|---|---|
| Official profit | 50 |
| Interest | 30 |
| Taxes | 15 |
| Wearing-out of machines and patents | 40 |
| Pay given as company shares | 10 |
| Factory closure costs | 8 |
| Expected future savings from a merger | 12 |
| **Adjusted EBITDA** | **165** |

Read it from top to bottom. The company starts at 50. It adds each line. It reaches 165.
The first four lines make the EBITDA of 135 from section 0.6. The last three lines are
add-backs, worth 30 in total.

The bridge is the most important object in this whole document. Footnote is about bridges.

### 0.9 The problem with bridges

Look again at Example Co. Three problems are hidden in its bridge.

1. **Each company makes its own rules.** Example Co. adds back "expected future savings."
   These savings have not happened yet. Another company does not do this. So the two final
   numbers do not mean the same thing.
2. **"One-off" costs can repeat.** If Example Co. closes a factory every quarter, the closure
   cost is not one-off. It is a normal cost of the business.
3. **The rules change quietly.** Next quarter, Example Co. can rename a line or add a new kind
   of add-back. It does not have to announce the change loudly.

### 0.10 Lenders: the people who need this

A **lender** is a person or firm that lends money to a company. Before lending, the lender
asks: "Can this company pay us back?"

Lenders look at debt compared to EBITDA. Many loan contracts have a limit, for example: "The
company's debt must stay below 4 times its EBITDA."

**Worked example (invented).** Example Co. owes 600.

- With the company's number: 600 ÷ 165 = **3.6 times**. This is below the limit.
- Without the "future savings" line: 600 ÷ 153 = **3.9 times**. This is very near the limit.

One line in the bridge changes the risk picture. For this reason, lenders do not trust the
company's number as it is. Today, an analyst copies each bridge into a spreadsheet by hand,
every quarter, for every company they follow. They check each line and remove the add-backs
they do not accept. This work is slow, boring and easy to get wrong.

### 0.11 How the ten ideas connect

```
Company makes profit ──► law makes it publish results ──► SEC website
        │
        ▼
Quarterly announcement ──► contains the bridge:
        official profit + interest, taxes, wearing-out = EBITDA
                        + add-backs                   = Adjusted EBITDA
        │
        ▼
Lender reads the bridge ──► removes add-backs it does not trust ──► decides on the loan
```

Footnote sits at the last step. It wants to do the lender's reading and checking work, for
every company, every quarter.

> **Remember (Unit 0)**
> - Public companies must publish their results on the free SEC website, every quarter.
> - Companies show a friendly profit number called Adjusted EBITDA.
> - The **bridge** is the table that walks from official profit to that number.
> - Each company picks its own add-backs, some repeat, and the rules change quietly.
> - Lenders depend on this number, and they rebuild every bridge by hand.

---

## Unit 1. What Footnote is, in one page

### 1.1 The one-sentence version

Footnote wants to be **the checked, dated and comparable record of how every US public company
calculates its Adjusted EBITDA**.

### 1.2 What it will do each quarter

When a company publishes its announcement, Footnote will:

1. **Collect** the announcement from the SEC website.
2. **Find** the bridge table in it.
3. **Read** every line and every number.
4. **Check** the arithmetic, and compare the starting number with the official data.
5. **Sort** each add-back into a standard group, for example "factory closure" or "merger."
6. **Link** each number to the exact sentence on the SEC website.
7. **Compare** the bridge with earlier quarters and report what changed.
8. **Calculate** a fair, comparable number, using rules that the customer can choose.

### 1.3 What the customer gets

The analyst does not copy bridges by hand. The analyst opens Footnote and sees, for each
company:

- the company's own bridge, checked;
- the fair number next to the company's number;
- every removed add-back, with the reason;
- an alert when the company changed its rules;
- a link from every number back to its source.

> **Remember (Unit 1)**
> Footnote does the lender's hand-copying work automatically. It adds checks, sources,
> change alerts and a fair number.

---

## Unit 2. The customer and the business

### 2.1 Who pays

The first customers are **credit analysts**. These are the people at lending firms who decide
whether a loan is safe. The plan names other similar groups too: firms that lend directly to
companies, and funds that buy risky company loans.

If interviews show that these people do not want Footnote, a backup group is ready. This group
is investors who check how "honest" a company's profit is. They need the same data. Only the
alerts and the screens would change.

### 2.2 Why they would pay

Four reasons make Footnote hard to copy. The project calls this the *moat*, like the water
around a castle.

1. **History that cannot be collected later.** Companies sometimes publish a past quarter
   again with different numbers. If you did not save the first version on the day it
   appeared, you cannot easily get it back. Footnote saves every version from the start.
2. **A standard set of rules, plus the customer's own rules.** A lending firm writes down its
   rules once ("we never accept future savings"). Footnote then applies them to every company.
   After that, the firm does not want to leave.
3. **Change alerts.** At least one existing data company (Daloopa) says in its own help pages
   that it joins renamed lines into one item and does not show changed past numbers by
   default. Footnote does the opposite: it shows these changes.
4. **Trust.** Every number links to its source. Footnote will publish its accuracy, with the
   number of test cases stated.

### 2.3 How the business starts

- **No spending until the first sale.** The owner decided that all services must be free until
  a customer pays. The plan uses only free tiers of online services.
- **Public data first.** Footnote starts with free SEC documents. Private documents that
  customers upload come much later.
- **Interviews before building.** The owner must talk to 8 analysts first. At least 5 must
  rebuild bridges by hand every quarter, and at least 3 must mention a price or ask to try
  the product. Also, fewer than half may say that an existing tool already does this job.
  If this test fails, the project switches to the backup group.
- **Early partners.** The first users get free or cheap access. In return, they give feedback.

> **Remember (Unit 2)**
> The first customer is the lender's analyst. Footnote saves history, applies the customer's
> rules, shows changes and proves every number. It spends nothing until someone pays, and it
> checks demand with interviews before it builds more.

---

## Unit 3. The fair number: how Footnote "normalizes"

To **normalize** means to apply one fixed set of rules to every company, so that the numbers
can be compared. The rules are in [NORMALIZATION.md](NORMALIZATION.md). That document is a
draft. Two analysts must review it before it becomes final.

### 3.1 Worked example first

Take the Example Co. bridge from Unit 0. Footnote looks at each add-back and gives it one of
three **treatments**:

| Line | Group | Draft treatment | Effect |
|---|---|---|---|
| Interest, taxes, wearing-out | Basic parts of EBITDA | **Accept** | Keep |
| Pay given as shares (10) | Share-based pay | **Flag** | Keep, but show a warning |
| Factory closure (8) | Restructuring | **Accept**, unless it repeats | Keep |
| Future merger savings (12) | Synergies | **Exclude** | Remove |

Calculation:

- Company's number: 165
- Minus excluded lines: 12
- **Fair number: 153**

Footnote shows the 153 *and* the reason: "Removed 12: future merger savings, line 7 of the
bridge, link to source."

### 3.2 The general rules

1. **Groups.** Each add-back goes into one standard group. The draft has 15 groups, for
   example: lawsuits, factory closures, merger costs, write-downs, currency changes, future
   savings, and "other."
2. **Treatments.** Each group has a default treatment: *accept*, *exclude* or *flag*. A flag
   never changes the number. It only warns the reader.
3. **The repeat rule.** If a group appears in 3 or more of the last 4 quarters, Footnote marks
   it as **repeating**. This rule is plain arithmetic, so it gives the same result every time.
   The draft has not decided yet whether a repeating item is removed automatically.
4. **The formula.** Fair number = company's number − the sum of all excluded lines.
5. **No guessing on bad data.** If the bridge lines do not add up to the company's total,
   Footnote does not calculate a fair number. It shows the reason instead.
6. **Versions.** Each version of the rules is fixed forever after it is published. Every fair
   number records which version made it.
7. **Customer rules.** Later, each customer can replace the default treatments with its own.

> **Remember (Unit 3)**
> Each add-back is sorted into a group. Each group is accepted, excluded or flagged. The fair
> number is the company's number minus the excluded lines, with every removal explained.

---

## Unit 4. How it works inside: the assembly line

Think of Footnote as an assembly line. A raw document goes in at one end. A checked bridge
comes out at the other end. Each station does one job.

### 4.1 Station by station, with Example Co.

| Station | Job | Example Co. | Part of the code today |
|---|---|---|---|
| 1. Collector | Download the announcement from the SEC website | Gets the Q2 announcement file | `ingestion/edgar/` |
| 2. Finder | Find the announcement among the attached files | Picks the main attachment | `ingestion/exhibit_99/` |
| 3. Table reader | Turn each table into rows and columns | Finds 12 tables | `extraction/html/table_parser.py` |
| 4. Bridge detector | Choose the table that is the bridge | Chooses the table with "Adjusted EBITDA" | `extraction/html/detector.py` |
| 5. Number cleaner | Fix size and direction of each number | "(12)" becomes −12; "in millions" multiplies by 1,000,000 | `extraction/scale_and_sign.py` |
| 6. Sorter | Put each line into a standard group | "Merger savings" → Synergies | `classification/taxonomy.py` |

Stations 1 to 6 exist today as separate parts. Nothing connects them automatically yet. A
person or a test runs them one after the other.

### 4.2 Two details that matter

**Size of numbers.** A table often says "in millions" at the top. The cell shows "165", but the
real value is 165,000,000. The number cleaner must apply this. If it misses it, every number is
wrong by a factor of a million.

**Direction of numbers.** A number in brackets, such as "(12)", means minus 12. A label such as
"Less:" also means subtract. The number cleaner must read both.

### 4.3 The two automatic checks

Footnote checks every bridge in two independent ways.

1. **The sum check.** Add all the lines. The total must equal the company's stated total.
   For Example Co.: 50 + 30 + 15 + 40 + 10 + 8 + 12 = 165. ✔
   Companies round each line, so a small gap is allowed. The gap allowed grows with the number
   of lines: about half a unit per line, and at least 1 unit.
2. **The starting-point check.** Companies also send the SEC their official numbers in a
   format that computers can read. Footnote compares the first line of the bridge (official
   profit, 50) with that official data. They must be the same.

If a check fails, a person reviews the bridge. If a line label does not match the official
data, the result is "review," not "fail."

### 4.4 Every number carries its address

Each number that Footnote reads keeps two things:

- the **original text** exactly as the company printed it, for example "(12.0)";
- a **locator**: the address of that number in the original document. It is like a street
  address for one cell of one table.

With the locator, a user can click a number and see the exact place on the SEC website.

### 4.5 The safety rules in the design

The code has automatic tests that stop anyone from breaking these rules:

1. **Only the collector uses the internet.** No other part can download anything.
2. **No AI in the number path.** No part of the code can call an AI model. Every number comes
   from fixed, repeatable code.
3. **Clear one-way order.** The table reader cannot reach back into the collector. The sorter
   cannot reach into the table reader. This keeps each station simple and testable.
4. **No hidden failures.** If a station skips something, it must say what it skipped and why.
   It never fills in a guess to look successful.

> **Remember (Unit 4)**
> Six stations: collect, find, read tables, choose the bridge, clean numbers, sort lines. Two
> checks: the sum and the starting point. Every number keeps its original text and its
> address. Only one part uses the internet, and no AI touches a number.

---

## Unit 5. How Footnote proves it works: the answer key

A program that reads tables can look correct and still be wrong. So Footnote measures itself
against an **answer key**. The project calls it the *gold set*.

### 5.1 How the answer key was made

1. **Choose the companies.** The engineering side proposed 15 companies with large debts, for
   example TransDigm, Caesars, Hertz and Carvana. The owner approved the list.
2. **Save the documents.** For each company, two quarterly announcements were saved. That is 30
   announcements. Each saved file has a fingerprint (a code that changes if one character
   changes) and its SEC web address.
3. **Draft the answers.** A tool read each bridge and ran the two checks from Unit 4.
4. **Get a second reader.** An AI model read the same 30 saved documents directly, without the
   tool. This is the only place where the project lets an AI read numbers, and the result is
   used only to test. It is never shown to customers.
5. **Compare.** Where the tool and the AI agreed, the answer was accepted. Where they disagreed,
   the owner looked at the document and decided.
6. **Record who checked each answer.** Every answer has a field `verified_by`, with one of three
   values: `tieout` (passed the checks), `model_agreement` (tool and AI agreed), or `human`
   (the owner decided).

The final answer key has **1,304 values**. Of these, 1,297 come from agreement and 7 were decided
by the owner.

### 5.2 The grader

A program called the **scorer** compares the extractor's output with the answer key. It
reports:

- **table found:** did it choose the right table?
- **exact match:** did it get the right line, period and number?
- **size:** did it apply "in millions" correctly?
- **direction:** did it get plus and minus right?

Each result is shown in total and separately for each `verified_by` value. So a reader always
sees how much of the key a human checked.

### 5.3 The first honest result

The first run of the current code (17 October 2026) scored 1,202 values:

| Measure | Result |
|---|---|
| Right table found | 60.7% |
| Exact match | 15.5% |
| Size correct | 0.0% |
| Direction correct | 49.4% |

These numbers are low, and that is expected. They are the **starting line**, not the finish.
They also show exactly what to fix:

- the bridge detector often ranks the right table 2nd to 8th, not 1st;
- the table reader often keeps only the year of a column, so it cannot tell "three months
  ended June 2026" from "six months ended June 2026";
- the size from "in millions" is not yet passed to the number cleaner.

An automatic check now stops any code change that makes the scores worse. The target for
Phase 2 is 95%.

> **Remember (Unit 5)**
> The answer key is 30 real announcements, checked by a tool, an AI second reader and the owner.
> A grader scores the code against it. The first scores are low and honest, and they show the
> next fixes.

---

## Unit 6. Where the project is today

### 6.1 The phases

Footnote is built in stages called **phases**. A phase opens only when the previous phase passes
a measurable test. The test is called a **gate**. Dates do not matter; only gates matter.

| Phase | Name | Gate (simplified) |
|---|---|---|
| 0 | Prove the basics | Answer key done, grader running, interviews pass, rules reviewed |
| 1 | Collect at scale | 50 companies × 8 quarters collected, no unexplained failures |
| 2 | Read bridges well | 95% of answers exactly right |
| 3 | Checking work and change alerts | 150 companies, alerts mostly correct |
| 4 | First product for partners | 3 partners use it weekly, 1 pays |
| 5 | Commercial scale | 10 paying firms |
| 6 | Extras | Each needs a written decision and customer demand |

### 6.2 Phase 0 status

**The project is in Phase 0.** Three of the five gate items are met (the last two count after
the waiting code is approved and merged):

| Gate item | Status |
|---|---|
| Answer key of 30 announcements, all checked | ✔ Met |
| Grader running automatically on every change | ✔ Met (after merge) |
| First result published | ✔ Met (after merge) |
| 5 of 8 analyst interviews pass | ✘ 0 of 8 done |
| 2 analysts review the rules for the fair number | ✘ 0 received |

### 6.3 What is waiting, and who must do it

All open items need a person. Software cannot do them.

1. **The owner** must approve the waiting code. The work is ready, in a chain of pull requests.
2. **The owner** must read and approve the draft rules for the fair number.
3. **The owner** must recruit and interview 8 analysts, with the ready interview script.
4. **Two of those analysts** must critique the rules.
5. **The owner** must check some grader results by hand against the SEC website.

Phase 1 cannot start until items 3 and 4 are done.

### 6.4 What does not exist yet

There is no website, no database, no automatic schedule and no customer. This is on purpose.
The project rules forbid building them before their phase.

> **Remember (Unit 6)**
> Phase 0 of 7. The engineering work is done. The remaining work is human: approvals,
> interviews and an expert review of the rules.

---

## Unit 7. The finished product

### 7.1 What the analyst will see (Phase 4 and later)

1. The analyst signs in and searches for a company.
2. The company page shows its bridges for many quarters, side by side.
3. Each number is a link. A click opens the exact place in the SEC document.
4. Next to the company's number is the fair number, with each removal listed.
5. A comparison shows how much this company adds back compared with similar companies.
6. A watchlist sends a weekly email: "3 of your companies changed their bridge."
7. The analyst can download everything to Excel, with formulas and source notes.

Later (Phase 5), each firm saves its own rules, and coverage grows to about 1,000 companies.

### 7.2 What it will look like inside

The assembly line from Unit 4 gets the missing parts:

1. **A schedule.** A free automatic job runs every day and collects new announcements.
2. **A file store.** Each original document is saved once, with its fingerprint, and never
   changed.
3. **A database with two areas.**
   - A **shared area** for public SEC data. All customers see the same facts.
   - A **private area** for each customer firm: its users, watchlists, notes and own rules.
     One firm can never read another firm's private area.
4. **Observations, never overwrites.** Every number is saved as an *observation*: "this
   document, on this date, said this line was 8." If a later document says 7, Footnote saves a
   second observation. It never deletes the first.
   - The first observation is "as first reported."
   - The latest is "current."
   - Two different observations for the same line and quarter are a **restatement**. This is
     exactly what the change alerts report.
5. **A failures list.** Every skip or error goes into a list with the station and the reason.
6. **A data service and a website** that read from the database. Customers never trigger
   calculations. They only read checked results.

### 7.3 The people work that stays

A person still reviews:

- new line labels that Footnote has not seen for that company before;
- bridges that fail a check.

Companies reuse the same labels every quarter. Footnote remembers each company's labels, so this
review shrinks over time. The plan estimates about 1 to 2 hours per quarter at 1,000 companies,
after a one-time setup.

If this work grows too large, an AI may *suggest* a group for a new label. A person must
confirm it. The AI can never produce or change a number.

> **Remember (Unit 7)**
> The finished product collects automatically, saves every version, keeps each customer's data
> private, and shows checked bridges, fair numbers and change alerts with a source link on
> every number.

---

## The whole picture on one page

```
SEC website ──► 1 Collect ──► 2 Find announcement ──► 3 Read tables ──► 4 Choose bridge
                                                                            │
   Customer ◄── Website / Excel / email ◄── Fair number ◄── 6 Sort lines ◄── 5 Clean numbers
                                                 ▲                 │
                                       customer's own rules   Checks: sum + starting point
                                                                   │
                                                     pass ──► saved as observations
                                                     fail ──► person reviews, reason recorded
```

---

## Quick reference: words used in this document

| Word | Meaning |
|---|---|
| Add-back | A cost that the company puts back to make its profit look larger |
| Adjusted EBITDA | The company's own friendly profit number |
| Answer key (gold set) | 30 real announcements with checked answers, used to grade the code |
| Bridge | The table from official profit to Adjusted EBITDA |
| Exclude / accept / flag | Remove / keep / keep with a warning |
| Fair number (normalized EBITDA) | The company's number after Footnote's rules remove some add-backs |
| Gate | The measurable test that a phase must pass |
| Lender / credit analyst | The person who decides if a loan is safe; Footnote's first customer |
| Locator | The address of one number in the original document |
| Observation | One saved fact: what one document said about one line on one date |
| Quarter | A three-month period |
| Restatement | A company publishes a past number again with a different value |
| SEC | The US government office that publishes company results |
| `verified_by` | The record of who checked an answer: the checks, tool-AI agreement, or a human |
