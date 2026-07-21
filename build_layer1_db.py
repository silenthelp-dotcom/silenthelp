r"""Regenerate the SilentHelp Layer 1 database (schema 4.0.0-regex).

Builds layer1_db/level{1,2,3}*.json from the component word lists below,
compiling each regex template the way the JSON documents it: slots joined by
\s+, each slot an alternation sorted longest-first, wrapped in (?<!\w)...(?!\w).

Edit the component lists here, re-run this script, and layer1.py picks the new
vocabulary up on its next import.
"""
import json, re
from pathlib import Path

OUT = Path(__file__).resolve().parent / "layer1_db"
OUT.mkdir(parents=True, exist_ok=True)

def alt(words):
    return "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))

def build(slots, comps):
    body = r"\s+".join(f"(?:{alt(comps[s])})" for s in slots)
    return r"(?<!\w)" + body + r"(?!\w)"

def combos(slots, comps):
    n = 1
    for s in slots:
        n *= len(set(comps[s]))
    return n

MATCHING = {
    "flags": ["case_insensitive", "unicode"],
    "normalization": "Normalize curly apostrophes, lowercase, and collapse whitespace before scanning.",
    "execution": "Compile each regex once locally. A match is only a candidate; Layer 2 must reject quotations, fiction, news, jokes, negation, reclaimed language, and educational discussion.",
}

SELF_STARTERS = ["i am","i'm","im","i feel","i've been feeling","ive been feeling","honestly i am","honestly i'm","honestly im","ngl i am","ngl i'm","ngl im","lowkey i am","lowkey i'm","lowkey im","highkey i am","highkey i'm","highkey im","bro i am","bro i'm","bro im","fr i am","fr i'm","fr im","right now i am","right now i'm","right now im","lately i am","lately i'm","lately im","these days i am","these days i'm"]

CONTEXTS = ["because of work","because of school","because of this test","because of the exam","because of the finals","because of this class","because of my homework","because of this assignment","because of this project","because of my job","because of my boss","because of my teacher","because of my professor","because of my family","because of this relationship","because of money","because of everything happening","from all this pressure","from the workload","from studying nonstop","with everything going on","and i cannot focus","and i cannot sleep","and i need a break","and nobody seems to notice","and it keeps getting worse","and i do not know what to do","and i feel stuck","and i cannot keep up","and i am falling behind","and my brain will not shut off","and i have no energy left","and i cannot deal with people","and i need help","and i am losing motivation","and i am barely getting through the day"]

TIME = ["today","right now","this week","lately","these days","at the moment","tonight","this morning","after today","since yesterday","all day","for days"]

# ---------------------------------------------------------------- level 1
L1 = {
    "self_starters": SELF_STARTERS,
    "modifiers": ["a little","kinda","kind of","pretty","really","so","super","lowkey","honestly","damn","freaking","genuinely"],
    "states": ["stressed out","tired from work","tired from studying","worn out today","mentally tired","running low on energy","having a rough day","having a bad day","struggling to focus","falling behind","swamped with work","buried in homework","fried for the final","fried for the finals","cooked for this exam","cooked for the final","low on social battery","out of social battery","in need of a break","annoyed with this assignment","frustrated with this project","dreading work tomorrow","dreading school tomorrow","doomscrolling again","stuck in tab hell","dealing with notification overload","sick of this test","sick of this class","done with this homework","over this assignment","not feeling productive","having trouble concentrating","unable to stay focused","sleepy all day","drained after work","drained after class","fed up with studying","behind on deadlines","overloaded with tasks","too busy to rest","ready for a break","needing some space","having zero motivation","stressed about the deadline","worried about the exam","nervous about the test","irritated by everything","exhausted from the commute","tired of meetings","tired of notifications","burned out from studying","burnt out from work","running on low battery","barely awake","not in the mood today","having a stressful week"],
    "contexts": CONTEXTS,
    "time": TIME,
    "other_speakers": [f"{s} {v}" for s in ["he is","he's","she is","she's","they are","they're","my friend is","my roommate is","my coworker is","my classmate is","my partner is","this student is","the person i'm talking to is","the person im talking to is"] for v in ["saying they are","telling me they are","acting","seeming","sounding"]],
}

# ---------------------------------------------------------------- level 2
L2 = {
    "self_starters": SELF_STARTERS,
    "modifiers": ["extremely","completely","seriously","really","so","way too","fucking","freaking","damn","insanely","unbelievably","genuinely","highkey","actually","totally","absolutely"],
    "states": ["overwhelmed by everything","unable to handle this pressure","at my breaking point","close to a breakdown","having a breakdown","having a meltdown","spiraling out of control","panicking about everything","in a full panic","unable to calm down","barely holding it together","losing control","emotionally exhausted","completely burned out","severely burnt out","too stressed to function","too anxious to think","unable to sleep from stress","drowning in pressure","crushed by this workload","not coping at all","shutting down from stress","crashing out over this","about to crash out","going through a mental breakdown","scared of what might happen","unable to keep pretending","falling apart emotionally","having nonstop panic","trapped in constant anxiety","losing sleep every night","unable to get out of bed","crying from the pressure","shaking from anxiety","feeling completely helpless","unable to deal with anyone","at the end of my rope","close to snapping","on the verge of a breakdown","not okay at all","desperate for help","unable to think clearly","feeling mentally wrecked","struggling to make it through today","unable to manage basic tasks","feeling like everything is collapsing","terrified about what comes next","feeling crushed and alone","unable to stop spiraling","in serious emotional distress","feeling completely hopeless","running out of ways to cope","losing my grip","unable to take much more","feeling unsafe around someone","being harassed constantly","being followed by someone","being threatened by someone","afraid to go home","afraid to be alone","scared someone will hurt me","under unbearable pressure"],
    "contexts": CONTEXTS,
    "time": TIME,
    "other_speakers": ["he said he is","he said he's","she said she is","she said she's","they said they are","they said they're","my friend told me they are","my roommate told me they are","my coworker said they are","my classmate said they are","my partner said they are","the person i'm talking to says they are","the person im talking to says they are","he sounds","she sounds","they sound","my friend sounds","my roommate sounds","my coworker sounds","my partner sounds"],
}

# ---------------------------------------------------------------- level 3
INTENSIFIERS = ["really","actually","fucking","seriously","definitely","straight up","deadass","fr","no cap","for real","finally","probably","literally","honestly","truly","genuinely"]
TIME_IMM = ["today","tonight","right now","after work","after school","after class","tomorrow","this weekend","when i see them","the next time i see them","before the day ends","as soon as i can"]
REASON = ["because they keep pushing me","because they ruined everything","because they will not stop","because they made me furious","because they keep threatening me","because they hurt me","because they humiliated me","because they betrayed me","because they crossed the line","because i cannot take this anymore","because i am losing control","because i am done being ignored","because they deserve to pay","because they keep stressing me out","because of what they said","because of what they did","because they will not leave me alone","because they keep harassing me","because they made my life hell","because nobody will stop them","because i feel trapped","because i am furious","because i cannot calm down","because everything is falling apart","because i have had enough","because they keep coming after me","because they keep mocking me","because they keep bullying me","because i want revenge","because i need this to end","because they keep testing me","because they are driving me insane"]

# Reported speech naturally shifts the reason clause to third person: "my friend
# said they want to kill themselves because THEY feel trapped". Without these the
# reported/threat templates only match if the reporter says "because I feel
# trapped", which is not how anyone reports someone else's crisis.
REASON_THIRD = REASON + [
    r.replace("because i ", "because they ")
    for r in REASON
    if r.startswith("because i ")
]

OWNERS = ["this","that","my","his","her","their","our"]
ROLE_TARGETS = ["teacher","professor","boss","coworker","classmate","roommate","neighbor","ex","manager","supervisor","coach","bully","attacker","stalker","harasser","enemy"]
PERSON_TARGETS = ["him","her","them","this guy","that guy","this dude","that dude","this man","that man","this woman","that woman","this person","that person","this student","that student","my partner","my boyfriend","my girlfriend","that bitch","this bitch","that asshole","this asshole","that motherfucker","this motherfucker","this nigga","that nigga","the person who did this","the person who hurt me","the person who threatened me","the person who betrayed me","the person who keeps bothering me","anyone who gets in my way","everyone in that room","people at my school","people at my job","the people responsible","their whole group"] + [f"{o} {r}" for o in OWNERS for r in ROLE_TARGETS]

L3 = {
    "intent_starters": ["i want to","i wanna","i'm going to","im going to","i am going to","i might","i may","i plan to","i'm planning to","im planning to","i feel like i could","i feel like i'm going to","i feel like im going to","lowkey i wanna","highkey i wanna","ngl i wanna","fr i wanna","tonight i might","today i might","i swear i'm going to","i swear im going to","i swear i'll","i swear ill","imma","i'm about to","im about to","i decided to","i intend to","i keep thinking i should","i cannot stop thinking i might","part of me wants to","i have been thinking about trying to","i am ready to","i feel pushed to","i am seriously considering trying to","i might actually"],
    "intensifiers": INTENSIFIERS,
    "self_harm_actions": ["kill myself","hurt myself","end my life","end it all","take my own life","unalive myself","delete myself","make myself disappear","stop being alive","leave this world","say goodbye forever","kms","commit suicide","die on purpose","do something irreversible to myself","make this my last day","never wake up again","not be here tomorrow","give up on living"],
    "violent_actions": ["kill","hurt","attack","stab","shoot","beat up","beat the shit out of","fuck up","destroy","take out","end","make disappear","come after","jump","ambush","seriously injure","put in the hospital","make pay","get revenge on","do something violent to","cause serious harm to","go after","threaten","terrorize"],
    "person_targets": PERSON_TARGETS,
    "time_or_immediacy": TIME_IMM,
    "reason_context": REASON,
    "reason_context_third": REASON_THIRD,
    "third_party_reporters": ["he said he wants to","she said she wants to","they said they want to","my friend said they want to","my roommate said they want to","my classmate said they want to","my coworker said they want to","my partner said they want to","my boyfriend said he wants to","my girlfriend said she wants to","he told me he is going to","she told me she is going to","they told me they are going to","the person i'm talking to says they want to","the person im talking to says they want to","the person messaging me says they want to","someone in the chat said they want to","he posted that he wants to","she posted that she wants to","they posted that they want to","he keeps saying he will","she keeps saying she will","they keep saying they will","my friend warned me they might"],
    "reported_crisis_actions": ["kill himself","kill herself","kill themselves","hurt himself","hurt herself","hurt themselves","end his life","end her life","end their life","die","commit suicide","unalive himself","unalive herself","unalive themselves","kill someone","hurt someone","attack someone","kill their teacher","hurt their teacher","attack their boss","kill their ex","hurt their family","make someone pay","do something irreversible","not be alive tomorrow","say goodbye forever"],
    "threat_subjects": ["he said he will","she said she will","they said they will","he threatened to","she threatened to","they threatened to","my ex threatened to","this person threatened to","my coworker threatened to","my classmate threatened to","my roommate threatened to","my neighbor threatened to","my boss threatened to","someone online threatened to","the person messaging me threatened to","he told me he would","she told me she would","they told me they would","he keeps saying he will","she keeps saying she will","they keep saying they will","this stranger said they will","that person said they will","someone in the chat said they will","my partner threatened to","my boyfriend threatened to","my girlfriend threatened to","my teacher threatened to","a student threatened to","a coworker threatened to","someone at school threatened to","someone at work threatened to"],
    "threat_actions": ["kill me","hurt me","attack me","stab me","shoot me","kill my family","hurt my family","come after me","find me and hurt me","wait for me outside","follow me home","make me disappear","seriously injure me","put me in the hospital","attack my friend","hurt my partner","kill my friend","come to my house","make me pay","do something violent to me","get revenge on me","hunt me down"],
}

def template(tid, slots, comps, note):
    return {"id": tid, "slots": slots, "join_with": "one_or_more_whitespace",
            "combination_count": combos(slots, comps), "regex": build(slots, comps), "note": note}

FILES = [
    ("level1_everyday_stress.json", 1, "Everyday stress", False, L1, [
        ("l1_self_contextual", ["self_starters","modifiers","states","contexts","time"], "Everyday stress expressed by the user or current speaker."),
        ("l1_other_contextual", ["other_speakers","modifiers","states","contexts","time"], "Everyday stress reported about the other participant or a third person."),
    ], ["screw this test","fuck this exam","this class is stressing me out","bro im so fried for the finals","i'm so done for the final","im so done for the final"]),
    ("level2_major_stress.json", 2, "Major stress", False, L2, [
        ("l2_self_contextual", ["self_starters","modifiers","states","contexts","time"], "Major stress expressed by the user or current speaker."),
        ("l2_other_contextual", ["other_speakers","modifiers","states","contexts","time"], "Major stress expressed by or reported about someone else."),
    ], ["i swear to god imma crashout","i'm having a meltdown","im having a meltdown","i can't take this pressure anymore","i cant take this pressure anymore","come suck my dick bitch","leave me the fuck alone","this person keeps stalking me"]),
    ("level3_crisis.json", 3, "Crisis: self-harm, harm to others, or lethal threats", True, L3, [
        ("l3_self_harm", ["intent_starters","intensifiers","self_harm_actions","time_or_immediacy","reason_context"], "Direct first-person self-harm or suicide intent."),
        ("l3_harm_others", ["intent_starters","intensifiers","violent_actions","person_targets","time_or_immediacy","reason_context"], "Direct intent to seriously harm another person."),
        ("l3_reported_crisis", ["third_party_reporters","intensifiers","reported_crisis_actions","time_or_immediacy","reason_context_third"], "Crisis language from the other participant or reported about a third person."),
        ("l3_threat_to_user", ["threat_subjects","intensifiers","threat_actions","time_or_immediacy","reason_context_third"], "Lethal or severe threat directed toward the user or another person."),
    ], ["imma kill this nigga today","i want to fucking kill this teacher","i want to fucking kill this guy","i'm going to kms","im going to kms","i want to kms","i wanna kms","i don't want to be alive anymore","i dont want to be alive anymore","i wish i was dead","i wish i were dead","everyone would be better off without me","cya in heaven","see you in heaven","it's ggs for me bro cya in heaven","its ggs for me bro cya in heaven","he says he wants to die","she says she wants to die","they say they want to die","he's going to kill me","hes going to kill me","she's going to kill me","shes going to kill me","go kill yourself","go kys","you should kill yourself"]),
]

for fname, level, name, bypass, comps, tmpls, exacts in FILES:
    templates = [template(t, s, comps, n) for t, s, n in tmpls]
    doc = {
        "schema_version": "4.0.0-regex",
        "level": level,
        "name": name,
        "bypasses_four_day_trend_gate": bypass,
        "matching": MATCHING,
        "components": comps,
        "regex_templates": templates,
        "exact_high_precision_phrases": exacts,
        "statistics": {
            "regex_template_count": len(templates),
            "exact_phrase_count": len(exacts),
            "theoretical_phrase_combinations": sum(t["combination_count"] for t in templates) + len(exacts),
        },
        "generated": "2026-07-21",
    }
    p = OUT / fname
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(fname, "->", p, sum(t["combination_count"] for t in templates), "combos")
