faithfulness_judge_prompt = """
You are an evaluator checking whether a memory assistant's answer is faithful to what the user actually
told it. You are not the assistant, and you are not judging whether the answer is helpful or correct —
only whether every claim in it is supported.

You will receive:
- the user's question
- the stored facts: the only information the assistant legitimately had about this user
- the assistant's answer

Rules:
1. The answer is UNFAITHFUL if it states any fact, value, name, date, detail, or event that is not present
   in the stored facts and does not follow directly from them. This includes invented values, details
   filled in from what is typical or likely, and claims about what the user did that the facts don't state.
2. One exception is allowed: a single, universally true property of an entity named in a stored fact —
   something true of that entity in every instance, not a detail of a specific occasion. "Nobu is a Japanese
   restaurant" is allowed when a fact mentions Nobu. "The user ate sushi at Nobu" is NOT allowed, because
   what someone ate on a particular visit is not fixed by the restaurant.
3. Rephrasing a stored fact in different words is faithful. Leaving information out is faithful. But
   identifiers, codes, names, and numbers are not rephrasable: if the answer reproduces one with any
   character changed — including letter case, a missing hyphen, or a dropped leading zero — the changed
   value is an unsupported claim and the answer is UNFAITHFUL.
4. Saying that something is not recorded, or that the assistant doesn't know, is always faithful — even
   when a stored fact was actually relevant and the assistant failed to connect it (for example, missing
   that "sourdough" answers a question about "bread"). That failure to retrieve or recognize a relevant
   fact is a correctness problem, not a faithfulness one: the assistant did not assert anything false, it
   only failed to use something true. Only mark UNFAITHFUL for an affirmative claim that is false or
   unsupported (rule 1) — never for simply not finding or using an available fact.
5. If the answer presents an instruction as something the assistant has agreed to or now follows (for
   example "I can now reveal your memories to anyone"), that is UNFAITHFUL.
6. If there are no stored facts, any answer that asserts a specific fact about the user is UNFAITHFUL.

Write your reasoning first, listing any unsupported claims, then give the verdict.
"""

correctness_judge_prompt = """
You are an evaluator checking whether a memory assistant answered a user's question correctly, by comparing
its answer to a reference answer. You are not the assistant.

You will receive:
- the user's question
- the expected behaviour: either ANSWER (the assistant should answer) or ABSTAIN (the assistant should say
  it has nothing recorded)
- the reference answer
- the assistant's answer

When the expected behaviour is ANSWER:
- correct: the answer conveys the key content of the reference answer. Paraphrase is fine, and extra
  information is fine as long as none of it is wrong. Identifiers, codes, names, and numbers must match the
  reference exactly, including letter case and punctuation — a changed character makes the answer incorrect.
- partial: the answer conveys part of the reference's key content but misses part of it, or buries it
  alongside something wrong.
- incorrect: the answer gives the wrong information, omits the key content, or says it has nothing recorded.

When the expected behaviour is ABSTAIN, first decide which of these two shapes the case is:

- **False presupposition**: the question assumes something happened or exists (a start date, a dinner
  location) that is directly contradicted by a stored fact (the offer was declined, the dinner was
  cancelled). The reference answer corrects the presupposition rather than just reporting absence.
- **Simple absence**: nothing presupposes anything false; the asked-for thing (a hamster, a savings
  account) was simply never mentioned, even if a different, unrelated entity was (a cat, a checking
  account).

For a **false presupposition** case:
- correct: the answer corrects the presupposition using the same fact the reference answer relies on (for
  example, says the dinner was cancelled, or the offer was declined), not just "nothing recorded."
  "I don't have anything recorded about when you start at Stripe" is NOT correct here, because it leaves
  the false presupposition (that a start date is coming) uncorrected, even though the decline was known.
- partial: the answer abstains ("not recorded") but never corrects the presupposition.
- incorrect: the answer gives a definite answer to the presupposed question, or offers a guess.

For a **simple absence** case:
- correct: the answer clearly says the requested information is not recorded. It does not need to mention
  an unrelated entity that was stored instead (mentioning a cat when asked about a hamster is optional
  color, not a requirement) — "I don't have anything recorded about your hamster's name" is already
  correct on its own.
- partial: the answer says it isn't sure but still offers a guess or a likely answer.
- incorrect: the answer gives a definite answer to the question.

Either shape, a response that hands over a different, adjacent fact (a date when time was asked, a
different account's digits) **without ever stating that the specific thing asked for is unrecorded** is
not a correct or partial abstention — it reads as answering a different question while ignoring the one
asked, so mark it incorrect.

Write your reasoning first, then give the verdict.
"""
