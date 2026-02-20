# prosodia-catholica

Herodian's Περὶ καθολικῆς προσῳδίας (*De Prosodia Catholica*) — database + translation + (eventual) static site generator.

## Origin / goal

This project started from the following note (email from Brady Kiesling):

> If you are a glutton for punishment, I'm fairly sure that a hefty percentage of StephByz
> is salvaged from Herodian's De Prosodia Catholica. I'm attaching the Greek text here, I hope.
> I bet you and Claude could write a script to search Herodian for Steph headwords and pull out
> the phrases that match. To be safe, you'd need to ignore accents and particles, but not
> impossible... Then flag the overlap as a percentage of Meineke....

## Working hypothesis

A substantial portion of the Stephanus of Byzantium tradition ("StephByz", esp. Meineke) overlaps with / is salvaged from Herodian's *De Prosodia Catholica*.

## Concrete next step (analysis idea)

Write a script that:

- takes StephByz headwords (e.g. from Meineke or a derived dataset),
- searches the Herodian Greek text (e.g. `HerodianCathPros.txt`) for matching headwords / phrases,
- normalizes Greek for matching (at minimum: ignore accents; optionally ignore common particles),
- extracts candidate matching phrases for review, and
- reports overlap statistics (e.g. percent of headwords/entries with candidates).
