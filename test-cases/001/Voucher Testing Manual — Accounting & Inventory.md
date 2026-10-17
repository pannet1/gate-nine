# Voucher Testing Manual — Accounting & Inventory

Oct 16, 2026 · @Iyyasamy Murugesan

This manual walks a tester through the voucher entry screens (v4) now live in Rachis — sales, purchase and payment vouchers, in the Accounting & Inventory modules. Follow each checklist in order; tick items off as you go, and use the bug-report template at the end for anything that fails.

## Scope of this version

Test only what is confirmed built and landed on main as of 2026-10-16. Two features are explicitly frozen pending a GST consultant's review and must NOT be tested as if they were bugs:

- The ₹-per-unit vs ₹-on-whole-line distinction for a line discount (not specified, not coded)
- Any GST/e-invoice/tax treatment of a discounted invoice (current behaviour is frozen as-is)

Section "Do NOT report as bugs" at the end lists every other known gap. If something you see isn't in that list, it's worth reporting.

## Before you start

- [ ] You have a login to the test tenant (ask Murugan/Jashveer for the URL and credentials)
- [ ] At least one Customer and one Vendor/Supplier exist in the tenant
- [ ] At least 2–3 Items exist in the Item master, with a Rate and a GST% set
- [ ] You know the tenant's configured GST rates (ask — typically one of 0, 5, 12, 18, 28%)
- [ ] You have a way to take a screenshot (for bug reports)

Work through each test in order — later tests (discount, print) assume you already have a few posted vouchers from the earlier ones.

## The 9 voucher types to test

| Voucher | Cycle | Purpose |
| --- | --- | --- |
| Sales Invoice | Sales | Bill a customer for goods/services |
| Delivery Note (GDN) | Sales | Record goods dispatched to a customer |
| Credit Note | Sales | Sales return / reduce what a customer owes |
| Purchase Order | Purchase | Order goods/services from a vendor |
| GRN (Goods Receipt Note) | Purchase | Record goods received from a vendor |
| Purchase Bill | Purchase | Record the vendor's bill |
| Debit Note | Purchase | Purchase return / reduce what you owe a vendor |
| Receipt Voucher | Payment | Record money received from a customer |
| Vendor Payment | Payment | Record money paid to a vendor |

The two payment vouchers (Receipt, Vendor Payment) look different on screen — amount-first layout, no item lines — that is by design, not a bug.

**Not in this version — don't look for them:** Sales Order, Proforma Invoice, Journal Voucher, Stock Transfer, Expense Voucher, Delivery Challan, Work Order, Job Card.

## Test 1 — Header fields

Open a new **Sales Invoice**.

- [ ] Top block shows: Customer, Invoice date, Due date, Place of supply, Payment terms — Payment terms and the date fields sit opposite the Customer field
- [ ] Title area shows the voucher type on one line and the voucher number just below it
- [ ] A "▸ More details" link/disclosure is present — click it; it should reveal Salesperson / PO and similar secondary fields
- [ ] Pick a Customer whose GST state is known — Place of supply should show the state name with its 2-digit code, e.g. "Tamil Nadu (33)" (if you instead see a bare number like "33" with no name, note it — see known-gaps section)
- [ ] Payment terms field can be left blank (it's optional) and the voucher still saves

Repeat the same checks on a **Purchase Bill** and a **GRN**, swapping Customer for Vendor.

## Test 2 — Currency box

On any voucher with a Currency box (Sales Invoice, Purchase Bill, etc.):

- [ ] Default currency shown is the company's base currency (e.g. INR)
- [ ] If your tenant has multi-currency enabled: the dropdown lists only currencies the company has turned on, not every world currency
- [ ] Pick a non-base currency — an Exchange rate field should appear, auto-filled with a rate
- [ ] Switch back to the base currency — the Exchange rate field should disappear
- [ ] If your tenant does NOT have multi-currency enabled: the field should show the base currency as plain read-only text, no dropdown

This is a recently-landed feature — note anything that looks off here, even if minor.

## Test 3 — Line items

On a Sales Invoice, add a line:

- [ ] Pick an Item — its HSN/SAC code appears as a small line under the Item name (not its own column)
- [ ] Rate auto-fills from the item master; you can still overwrite it
- [ ] Enter a Qty — Amount computes automatically and is not editable
- [ ] GST% shows either as plain read-only text or as a dropdown of your tenant's configured rates — never a greyed-out/disabled dropdown
- [ ] Try typing a GST% that isn't one of your tenant's configured rates (e.g. 88%) — it should be rejected with a clear error
- [ ] Pressing Tab or Enter in the last cell of a row moves you to a new row automatically
- [ ] A fully-filled, error-free row gets a visual highlight showing it's complete

**Line discount** (on the same row):

- [ ] You can enter a discount on a line as either a percentage OR a flat ₹ amount
- [ ] Whichever mode you use, the line's Amount reduces correctly
- [ ] Save as draft, reopen the voucher — the line discount you entered is still there (this was a real bug until 2026-10-14; worth double-checking)

Do not try to test a "₹ per unit" vs "₹ on the whole line" distinction — that doesn't exist yet (see Scope).

## Test 4 — Header (invoice) discount

On a Sales Invoice with 2–3 lines already entered:

- [ ] A Discount control is visible near the totals, with a toggle for % or ₹
- [ ] Next to it, the "eligible base" figure is shown — this should equal the sum of all lines' amounts AFTER each line's own discount (not the raw line total)
- [ ] Enter a discount within range — it applies and totals update correctly

Now test the three rejection cases — each should show a clear inline error and block Save:

- [ ] Enter a negative discount
- [ ] Enter a % discount over 100%
- [ ] Enter a ₹ discount greater than the eligible base amount
- [ ] Open a **Purchase Bill** instead: even if your tenant has the invoice-discount setting turned OFF, the header discount field should still be present and usable (Purchase always records what the supplier billed)
- [ ] Open a **Credit Note** or **Debit Note**: the header discount should fold in correctly if the parent invoice/bill had one

This area was re-landed recently (PR #230) — test it deliberately rather than assuming it works.

## Test 5 — GST/tax

**Do test:**

- [ ] GST% on a line only accepts your tenant's configured rates (see Test 3)
- [ ] For an interstate sale (customer's state ≠ your company's state), tax splits as IGST
- [ ] For an intrastate sale, tax splits equally as CGST + SGST
- [ ] Create a Credit Note against an old invoice whose GST rate has since changed/been removed from Settings — the Credit Note should still show the ORIGINAL rate from that invoice, not today's rate

**Do NOT test / do not report as bugs:**

- Any GST or e-invoice treatment of a discounted invoice — frozen pending consultant review
- TCS and cess — both currently compute as zero
- Reverse Charge (RCM) purchases — no input-tax-credit leg yet
- GST on advance receipts — correctly computes zero (this is required by law for goods, not a bug)

## Test 6 — Draft, Post, Correct

- [ ] A new voucher shows "Save draft" and "Post" as the two buttons
- [ ] Save as draft, then open it again and click Post — it should become the SAME document (check the voucher number didn't change or duplicate), not a second copy
- [ ] After Post, the voucher stays on screen, now read-only — it should NOT clear itself automatically
- [ ] A posted voucher shows "Print", "More", and "Correct" actions
- [ ] Click "Correct" on a posted voucher — a banner appears and a reason is required before you can save the correction (a free-text note alone, with no reason category to pick, is a known gap — note which you see)
- [ ] Click "New" (or press Alt+N) — it should reset to a blank voucher

For GRN specifically: editing a draft GRN behaves a little differently from other vouchers (it can't change Vendor/PO once started) — that's expected, not a bug.

## Test 7 — Print / PDF

Post a Sales Invoice, then Print it (or download the PDF) and check:

- [ ] Left and right margins are present — text is not flush against the paper edge
- [ ] Payment Terms shows a readable label (e.g. "Net 30"), never a raw number/id
- [ ] Amount columns are right-aligned
- [ ] The discount column is headed "Disc (₹)"
- [ ] Date prints as dd-mm-yyyy
- [ ] Totals panel shows Discount, GST, and Round-off as separate lines
- [ ] If a UPI QR code is printed, it's a reasonable size, not oversized
- [ ] Repeat for a Purchase Bill and a Credit Note

Do not worry about paper size (A4/A5) or template choice (Classic/Modern/Minimal/Professional) unless your tenant's Settings exposes those choices — flag if you can't find a way to print at all, but don't chase missing template variety as a bug yet.

## Do NOT report these as bugs

- ₹-per-unit vs ₹-on-whole-line discount mode — not built
- Any GST/e-invoice treatment of discounts — frozen, pending consultant
- TCS and cess amounts showing zero
- Reverse Charge (RCM) purchases with no input-tax-credit leg
- GST on advance receipts showing zero
- Sales Order, Proforma Invoice, Journal Voucher, Stock Transfer, Expense Voucher, Delivery Challan, Work Order, Job Card — none of these exist yet
- GRN's draft edit behaving differently from other vouchers (can't change Vendor/PO)
- Correcting a posted Receipt or Vendor Payment amount — by design, only allocation can change, not the posted amount
- Changing quantities on a posted GDN — restricted by design; use reversal/reissue instead
- Missing A4/A5 or print-template choice if your tenant's Settings don't expose them yet
- Place of supply showing a bare 2-digit code instead of a state name — known gap, already backlogged

## How to report a problem

For each issue, send:

1. Voucher type and test number (e.g. "Test 4, Sales Invoice")
2. What you did, step by step
3. What you expected
4. What actually happened — with a screenshot
5. The voucher number, if one was created

Send these to Murugan directly rather than filing them anywhere else.
