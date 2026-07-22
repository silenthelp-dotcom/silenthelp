"""
Layer 1 detection test corpus.

Two things matter and they pull in opposite directions:
  * RECALL   — real distress must not be missed (a miss is the whole product failing)
  * PRECISION— everyday speech, jokes, and idioms must not fire (false alarms
               train the user to ignore the app)

Each case is (text, min_level, max_level). Use max_level=0 for "must stay silent".
Levels: 0 none · 1 low · 2 moderate · 3 high · 4 crisis.

Run:  python3 test_layer1.py
"""

import layer1

# (text, min_level, max_level)
CASES = [
    # ---------------------------------------------------------------- benign
    ("what time does the library close", 0, 0),
    ("can you send me the notes from bio", 0, 0),
    ("i'm going to the store after work", 0, 0),
    ("the exam is on tuesday right", 0, 0),
    ("i finished my homework finally", 0, 0),
    ("that movie was so good bro", 0, 0),
    ("i am going to kill this presentation tomorrow", 0, 0),
    ("we killed that game last night", 0, 0),
    ("my phone is dead", 0, 0),
    ("i'm dying to see the new season", 0, 0),
    ("this cake is to die for", 0, 0),
    ("she's a hopeless romantic", 0, 0),
    ("i cut myself a slice of pizza", 0, 0),
    ("cutting onions makes me cry", 0, 0),
    ("suicide squad was mid", 0, 0),
    ("the suicide prevention hotline number is on the poster", 0, 0),
    ("dead serious that was the best play", 0, 0),
    ("the group chat is dead", 0, 0),

    # ------------------------------------------------------- jokes / hyperbole
    ("bro im dying laughing lmao", 0, 0),
    ("this meme killed me 😂", 0, 0),
    ("im dead lmaooo", 0, 0),
    ("i want to die lol this homework", 0, 1),
    ("kill me now hahaha jk", 0, 1),
    ("the suspense is killing me", 0, 0),

    # ------------------------------------------------- level 1 everyday stress
    ("im really stressed out because of work today", 1, 2),
    ("i'm so tired from studying because of the finals lately", 1, 2),
    ("honestly im pretty swamped with work because of my boss this week", 1, 2),
    ("ngl i'm kinda fried for the finals because of this class right now", 1, 2),
    ("screw this test", 1, 2),
    ("this class is stressing me out", 1, 2),
    ("bro im so fried for the finals", 1, 2),

    # --------------------------------------------------- level 2 major stress
    ("i'm completely overwhelmed by everything because of school lately", 2, 3),
    ("im absolutely at my breaking point because of my family right now", 2, 3),
    ("i'm seriously barely holding it together and i need help today", 2, 3),
    ("im having a meltdown", 2, 3),
    ("i can't take this pressure anymore", 2, 3),
    ("this person keeps stalking me", 2, 3),
    ("i swear to god imma crashout", 2, 3),

    # ------------------------------------------------------- level 4 crisis
    ("i wish i was dead", 4, 4),
    ("i wish i were dead", 4, 4),
    ("i don't want to be alive anymore", 4, 4),
    ("i dont want to be alive anymore", 4, 4),
    ("everyone would be better off without me", 4, 4),
    ("i want to kms", 4, 4),
    ("i wanna kms", 4, 4),
    ("im going to kms", 4, 4),
    ("cya in heaven", 4, 4),
    ("it's ggs for me bro cya in heaven", 4, 4),
    ("i want to fucking kill myself tonight because i cannot take this anymore", 4, 4),
    ("im going to seriously end my life today because i feel trapped", 4, 4),
    ("lowkey i wanna deadass unalive myself right now because they hurt me", 4, 4),
    ("i want to fucking kill this teacher", 4, 4),
    ("imma kill this nigga today", 4, 4),
    ("im going to fucking hurt my bully after school because they keep bullying me", 4, 4),

    # ------------------------------- crisis reported about / by a third party
    ("he says he wants to die", 4, 4),
    ("she says she wants to die", 4, 4),
    ("they say they want to die", 4, 4),
    ("my friend said they want to seriously kill themselves tonight "
     "because they feel trapped", 4, 4),
    ("he keeps saying he will actually die tomorrow because i cannot take this anymore",
     4, 4),

    # --------------------------------------------- threats directed at the user
    ("he's going to kill me", 4, 4),
    ("shes going to kill me", 4, 4),
    ("he threatened to fucking kill me tonight because they hurt me", 4, 4),
    ("my ex threatened to seriously hurt my family right now because i want revenge",
     4, 4),
    ("go kill yourself", 3, 4),
    ("you should kill yourself", 3, 4),
    ("go kys", 3, 4),
    ("i'm going to beat you up after school", 3, 4),
    ("watch your back", 3, 4),
    ("nobody likes you", 3, 4),
    ("you're worthless", 3, 4),

    # ----------------------------------------- misspellings (fuzzy safety net)
    ("im so depresed and alon", 3, 3),
    ("i feel so lonley and hopless", 3, 3),
    ("im exhuasted", 1, 1),
    ("feeling really overwelmed", 2, 2),
    ("im so anxous about everything", 2, 2),

    # ------------------------------------------- loose phrasing (recall check)
    ("i'm so burnt out and everything is pointless", 1, 4),
    ("i feel so alone", 3, 3),
    ("nothing matters anymore", 0, 4),
    ("i'm struggling", 2, 2),

    # ---------------------------------------------------- fuzzy false-positive
    # Ordinary English one edit away from an emotion word. Before the real-word
    # guard these all scored level 3 and would have popped an alert.
    ("we killed that game last night", 0, 0),
    ("that painting is sacred to them", 0, 0),
    ("i'm drawing a diagram for class", 0, 0),
    ("the recipe is painless honestly", 0, 0),
    ("countless people showed up", 0, 0),
    ("my beloved dog turned ten", 0, 0),
    ("walk along the river", 0, 0),
    ("i tied my shoes and timed the run", 0, 0),
    ("she's envious of his grades", 0, 0),
    ("the box was empty-handed nonsense", 0, 3),
    ("i hired a tutor and fired off the email", 0, 0),

    # ------------------------------------------- partial slot forms (recall)
    # The v4 templates originally required ALL five slots, so these all scored 0
    # and the database was effectively dead for real typing. Optional slots fixed
    # it: the state alone, with a starter, is enough.
    ("im stressed out", 1, 2),
    ("im really stressed out", 1, 2),
    ("im really stressed out because of work", 1, 2),
    ("im fried for the finals", 1, 2),
    ("i feel worn out today", 1, 2),
    ("i'm completely overwhelmed by everything", 2, 3),
    ("i am at my breaking point", 2, 3),
    ("i want to kill myself", 4, 4),
    ("i wanna hurt myself", 4, 4),
    ("imma kill him", 4, 4),
    ("he threatened to kill me", 4, 4),
    ("my friend said they want to kill themselves", 4, 4),

    # -------------------------- short idiomatic distress (exact phrase lists)
    # No <starter><modifier><state> decomposition exists for these, so the slot
    # grammar can never match them; they must be listed literally.
    ("i hate myself", 2, 3),
    ("i hate my life", 2, 3),
    ("i give up", 2, 3),
    ("nobody cares about me", 2, 3),
    ("everything is falling apart", 2, 3),
    ("i'm all alone", 2, 3),
    ("i don't want to be here", 4, 4),
    ("i want to disappear", 4, 4),
    ("i can't go on", 4, 4),
    ("no reason to live", 4, 4),
    ("i'd be better off dead", 4, 4),

    # --------------------------------- emotion words about someone/something else
    # The fuzzy pass had no notion of WHOSE feeling it was, so these scored the
    # same level 3 as "i am depressed".
    ("the movie was so sad", 0, 0),
    ("the ending was sad", 0, 0),
    ("my dog looks sad", 0, 0),
    ("sad news about the team", 0, 0),
    ("that story is depressing", 0, 0),
    ("she seems tired", 0, 0),
    ("my friend is stressed", 0, 1),
    # ...but first-person still fires
    ("im so sad", 3, 3),
    ("i feel sad", 3, 3),
    ("i have been feeling worthless", 3, 3),

    # --- Root vocabulary: database phrases must fire BARE, with no starter ---
    # Before the root pass, every one of these scored 0: the regex templates
    # only matched a full <starter><modifier><state><context> sentence, so the
    # databases' own vocabulary was unreachable on its own.
    ("kill myself", 4, 4),
    ("commit suicide", 4, 4),
    ("kms", 4, 4),
    ("end my life", 4, 4),
    ("take my own life", 4, 4),
    ("unalive myself", 4, 4),
    ("never wake up again", 4, 4),
    ("i want to die", 4, 4),
    ("i wanna die", 4, 4),
    ("better off dead", 4, 4),
    ("i have nothing to live for", 4, 4),
    ("i dont want to be alive", 4, 4),
    # gerunds — the db stores "hurt myself", people write "hurting myself"
    ("i have been thinking about hurting myself", 4, 4),
    ("thinking about killing myself", 4, 4),
    ("ive been cutting myself", 4, 4),
    ("starving myself", 4, 4),
    # self-harm methods added to the crisis db
    ("i want to overdose", 4, 4),
    ("im going to hang myself", 4, 4),
    ("i slit my wrists", 4, 4),
    # violent action + person target, no starter slot needed
    ("im going to kill him", 4, 4),
    ("i wanna stab that guy", 4, 4),
    ("beat the shit out of my roommate", 4, 4),
    # distress roots
    ("at my breaking point", 2, 4),
    ("having a breakdown", 2, 4),
    ("having a meltdown", 2, 4),
    # Reaches crisis via the ideation vocabulary ("cant do this anymore"), not
    # just major stress — deliberate after the v2 merge.
    ("i can't do this anymore", 2, 4),
    ("i cant handle this pressure", 1, 4),      # contraction of "cannot"
    ("i cannot handle this pressure", 1, 4),
    ("mentally tired", 1, 4),

    # --- Context: the SAME words joking must stay silent ---
    ("lol i wanna die that was so embarrassing", 0, 0),
    ("i wanna die of embarrassment lmao", 0, 0),
    ("haha i want to die", 0, 0),
    ("this homework makes me wanna die lol", 0, 0),
    ("im cutting the onions", 0, 0),
    ("cutting class today", 0, 0),
    ("cutting costs this quarter", 0, 0),
    ("i cut myself a slice of cake", 0, 0),
    ("cut myself off from everyone", 0, 0),
    ("i cut myself short during the presentation", 0, 0),
    ("i could kill for a coffee", 0, 0),
    ("i need to kill this bug in my code", 0, 0),
    ("i am so tired of waiting for the bus", 0, 0),
    ("im sick and tired of this weather", 0, 0),
    ("suicide squad was mid", 0, 0),
    ("the character will die in chapter 3", 0, 0),
    ("beat the eggs until fluffy", 0, 0),
    ("lets end class early", 0, 0),

    # --- ...but an explicit crisis phrase is NEVER masked by a joke marker ---
    ("lol i want to kill myself", 4, 4),
    ("haha im gonna commit suicide fr", 4, 4),
    ("lmao kms", 4, 4),
    ("i am done with this homework and want to kill myself", 4, 4),

    # --- Glue words must never fire alone ---
    ("him", 0, 0),
    ("really", 0, 0),
    ("today", 0, 0),
    ("that guy", 0, 0),
    ("i am going to the store", 0, 0),
]


def main() -> int:
    fails = []
    for text, lo, hi in CASES:
        r = layer1.scan(text)
        lvl = r["level"]
        if not (lo <= lvl <= hi):
            fails.append((text, lo, hi, lvl, r["categories"]))

    print(f"{len(CASES) - len(fails)}/{len(CASES)} passed")
    for text, lo, hi, lvl, cats in fails:
        print(f"  FAIL want {lo}-{hi} got {lvl} {cats} :: {text}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
