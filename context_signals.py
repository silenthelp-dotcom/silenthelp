"""
SilentHelp — context, intent and joke-vs-serious signals (local, no AI)
=======================================================================

Layer 1's databases answer "is a risk WORD here?". This module answers the
questions a counselor actually asks next:

  * Is there a real risk signal, even with no keyword?   ("everyone would be
    better off", "i have the pills saved up", "this is my last message")
  * Is this a joke / hyperbole about something external? ("kms this test 💀")
  * What did the earlier messages in this conversation say?  ("lol jk" right
    after "nobody would care if i was gone" is NOT reassurance)

layer1.scan() calls assess() and applies the result as a FLOOR (can only raise)
and, for clear jokes with nothing else going on, a CAP (lowers severity).

SAFETY RULES (enforced in assess(), covered by tests/detection/):
  1. When unsure, lean serious. Ambiguous hopelessness scores at least "low".
  2. A joke marker can LOWER severity, never erase an explicit self-harm term:
     "kms this test 💀" -> low (logged), not none.
  3. A joke never lowers anything that carries a REAL risk signal: a plan,
     means/access, a timeline, a location ("on the bridge right now"),
     goodbye language, passive ideation, self-harm behaviour, abuse, a
     "not joking" marker, or risk earlier in the same conversation.
  4. Earlier risk in the conversation raises later messages: a retraction,
     deflection or minimisation ("jk", "nvm", "i'm fine", "anyway...") after a
     disclosure is treated as a warning sign, not an all-clear.

Everything here is plain regex over normalised text: free, offline, and fast.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _rx(*parts: str) -> "re.Pattern":
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


_I = r"(?:i|i'm|im|i've|ive|i'd|id|i'll|ill|i am|i have)"
_SELF = r"(?:me|myself|my\s+life)"
_TIME = (r"(?:tonight|tonite|2nite|tomorrow|tmrw|tmr|this\s+weekend|this\s+week|"
         r"(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
         r"after\s+school|before\s+school|right\s+now|rn|soon|in\s+an?\s+hour|"
         r"when\s+every(?:one|body)(?:'s|\s+is)\s+asleep|today|later\s+tonight|"
         r"by\s+the\s+end\s+of\s+the\s+(?:day|week))")

# "no point" / "what's the point" are existential only when they are not
# about a specific task: "what's the point of this worksheet" is a complaint.
_EXISTENTIAL_ONLY = (r"(?!\s+(?:of|in|to|for|with|doing|going\s+to)\s+"
                     r"(?!(?:anything|living|life|trying|going\s+on|it\s+all|any\s+of\s+(?:it|this)|"
                     r"being\s+(?:here|alive)|me|myself|existing|getting\s+up)\b))")

# ---------------------------------------------------------------------------
# RISK signals — each maps to a minimum level (0-4 scale used by layer1)
# ---------------------------------------------------------------------------

# Explicit first-person statements the database misses (crisis).
_EXPLICIT = _rx(
    r"\b(?:i'?m|im|i\s+am|i\s+feel|feeling|i'?ve\s+been|been|getting)\s+(?:so\s+|really\s+|very\s+|kinda\s+|lowkey\s+|pretty\s+)?suicidal\b",
    r"^\W*(?:so\s+|very\s+)?suicidal\W*$",
    r"\b(?:i\s+have|i'?ve\s+been\s+having|having|i\s+get|i\s+keep\s+having)\s+suicidal\s+(?:thoughts|feelings|urges)\b",
    r"\b(?:think|thinking|thought)\s+(?:about|of)\s+(?:suicide|killing\s+myself)\b",
    r"\b(?:going\s+to|gonna|want\s+to|wanna|about\s+to|might|will|i'?ll|ill)\s+(?:just\s+)?end\s+it(?:\s+all)?\b(?!\s+(?:with|between))",
)

# Passive / indirect suicidal ideation with no database keyword.
_IDEATION = _rx(
    r"\b(?:every(?:one|body)|they|people|my\s+(?:family|parents|friends|mom|dad))(?:'d|\s+would|\s+will)\s+(?:all\s+)?be\s+(?:so\s+much\s+)?(?:better|happier|fine|okay|ok)(?:\s+off)?(?:\s+without\s+me|\s+if\s+i\s+(?:was|were|wasn'?t|weren'?t)\b.*|\s*(?:[.!?,…]|$))",
    r"\b(?:they'?d|everyone'?d|they\s+would|everyone\s+would)\s+be\s+(?:better|happier)\s+off\s*$",
    r"\b(?:would|will)\s+be\s+(?:so\s+much\s+)?(?:easier|better|happier)\s+(?:without\s+me|if\s+i\s+(?:was|were)\s+(?:gone|dead|not\s+here))",
    r"\bmaybe\s+(?:they|everyone|people)(?:'d|\s+would)\s+be\s+better(?:\s+off)?\b",
    r"\b(?:happier|better\s+off|easier)\s+if\s+i\s+(?:was|were|wasn'?t|weren'?t)\s+(?:gone|dead|here|around|alive|born)\b",
    r"\b(?:don'?t|dont|do\s+not)\s+see\s+(?:the|a|any)\s+point\b" + _EXISTENTIAL_ONLY,
    r"\b(?:not|never)\s+wake\s+up\b",
    r"\bsleep\s+(?:forever|for\s+ever|and\s+never)\b",
    r"\b(?:won'?t|will\s+not|wont|not\s+gonna|not\s+going\s+to)\s+be\s+(?:around|here|alive)\s+(?:much\s+longer|for\s+long|soon|anymore|by)\b"
    r"(?![^.?!]{0,40}\b(?:trip|vacation|visit|grandma\w*|grandpa\w*|camp|tournament|moving|appointment|going\s+to|out\s+of\s+town)\b)",
    r"\b(?:won'?t|wont|will\s+not)\s+be\s+(?:a|your|anyone'?s|my)\s+(?:problem|burden)\s+(?:much\s+longer|for\s+long|soon|anymore)\b",
    r"\bsoon\s+it\s+(?:won'?t|wont|will\s+not)\s+(?:be\s+my\s+problem|matter)\b",
    r"\b(?:i'?ll|ill|i\s+will)\s+be?\s*gone\s+soon\b|\b(?:i'?ll|ill|i\s+will)\s+b\s+gone\b",
    r"\bgone\s+soon\b",
    r"\b(?:stop|quit)\s+existing\b|\btired\s+of\s+(?:existing|being\s+alive|living|being\s+here|life)\b",
    r"\b(?:wonder|wondering|bet)\b[^.?!]{0,40}\bwould\s+(?:even\s+)?(?:cry|care|notice|miss\s+me|come\s+to\s+my\s+funeral|show\s+up)\b",
    r"\b(?:nobody|no\s+one|noone)\s+would\s+(?:even\s+)?(?:care|miss\s+me|cry)\b(?!\s+(?:about\s+(?!me\b)|if\s+(?:we|you|they|the)\b))",
    r"\b(?:nobody|no\s+one|noone)\s+would\s+(?:even\s+)?notice\s+if\s+i\s+(?:was|were|wasn'?t|weren'?t|disappeared|died|stopped\s+(?:showing\s+up|existing|coming|being)|vanished|left\s+forever|killed|just\s+(?:disappeared|vanished|stopped|left))",
    r"\bif\s+i\s+(?:was|were)\s+gone\b|\bif\s+i\s+(?:just\s+)?(?:disappeared|died|wasn'?t\s+here|stopped\s+existing)\b",
    r"\b(?:think|thinking|thought)\s+about\s+(?:not\s+being\s+(?:here|around|alive)|dying|death|ending\s+it)\b",
    r"\b(?:thinking|thought|think)\s+(?:about\s+)?how\s+to\s+(?:make\s+it\s+(?:all\s+)?stop|end\s+it|do\s+it|disappear)\b",
    r"\b(?:don'?t|dont|do\s+not)\s+want\s+to\s+(?:do\s+this|be\s+here|exist|keep\s+going|wake\s+up)\b",
    r"\bscared\s+(?:of\s+)?what\s+i\s+(?:might|could|would|will)\s+do\b",
    r"\b(?:don'?t|dont|do\s+not)\s+(?:really\s+)?care\s+what\s+happens\s+(?:to\s+me|anymore|$)",
    r"\b(?:wish|want)\s+(?:i\s+could\s+)?(?:to\s+)?(?:just\s+)?(?:disappear|vanish|stop\s+existing|not\s+exist)\b",
    r"\b(?:tomorrow|again)[.,!]?\s+or\s+ever\b|\bor\s+ever\s+again\b",
    r"\bending\s+it\s+all\b|\bend\s+it\s+all\b",
    r"\bwhat'?s\s+the\s+point\s+of\s+(?:living|life|being\s+alive|going\s+on)\b",
    r"\bkeep\s+thinking\s+about\s+(?:dying|death|ending\s+it|not\s+being\s+here)\b",
    r"\b(?:won'?t|wont|will\s+not|not\s+gonna|not\s+going\s+to|don'?t\s+think\s+i'?ll|dont\s+think\s+ill|don'?t\s+think\s+i\s+will)\s+be\s+(?:around|here)\s+(?:much\s+longer|for\s+(?:much\s+)?long|anymore)\b",
    r"\b(?:won'?t|wont|not\s+gonna|not\s+going\s+to)\s+be\s+a\s+(?:problem|burden|bother)\s+(?:for|to)\s+(?:anyone|anybody|you|them|everyone)\s+(?:much\s+longer|after|soon|anymore)\b",
    r"\b(?:think|thinking|thought)\s+about\s+(?:driving|crashing|swerving)\s+(?:my\s+car\s+)?(?:into\s+(?:a\s+|the\s+)?(?:wall|tree|pole|traffic|truck|oncoming|river|lake|ditch|guardrail)|off\s+(?:a\s+|the\s+)?(?:bridge|cliff|road|overpass))\b",
    r"\b(?:rather|prefer\s+to)\s+(?:die|be\s+dead)\s+than\s+(?:keep\s+)?(?:living|live|going\s+on|go\s+on|being\s+alive|be\s+alive|being\s+here|be\s+here|being\s+me|wake\s+up|feel\s+like\s+this|feeling\s+like\s+this)\b",
    r"\bthinking\s+(?:about|of)\s+how\s+(?:to|i\s+(?:could|would|can))\s+(?:make\s+it\s+(?:all\s+)?stop|end\s+it|do\s+it|not\s+wake\s+up|disappear)\b",
)

# A concrete plan or decision.
_PLAN = _rx(
    rf"\b(?:planning|planned|plan)\s+(?:how|to\s+(?:do\s+it|end|kill|go|die))\b|\bhave\s+a\s+plan\b|\bmade\s+a\s+plan\b",
    r"\bhow\s+i'?d\s+do\s+it\b|\bhow\s+i\s+would\s+do\s+it\b|\bhow\s+i'?m\s+(?:gonna|going\s+to)\s+do\s+it\b",
    r"\b(?:figured|worked)\s+out\s+how\b",
    r"\b(?:already|finally)\s+decided\b|\bmade\s+up\s+my\s+mind\b|\bit'?s\s+decided\b",
    r"\b(?:tonight|today)\s+is\s+the\s+night\b|\bit'?s\s+(?:time|happening)\s+(?:tonight|today)\b",
    r"\b(?:looked|looking|look)\s+up\s+how\s+(?:many|much|to)\b",
    r"\bhow\s+many\b[^.?!]{0,40}\bwould\s+(?:it\s+)?take\b",
)

# Access to lethal means (possession / location), not a hyperbolic mention.
_MEANS = _rx(
    # stockpiling medication ("saved up", "all of", "a whole bottle", "enough")
    r"\b(?:saved|saving|stockpil\w*|hoard\w*|collect\w*|hiding|hid|hidden)\b[^.?!]{0,25}\b(?:pills?|meds|medication|painkillers|tylenol|xanax)\b",
    r"\b(?:pills?|meds|painkillers)\b[^.?!]{0,15}\b(?:saved\s+up|ready|stashed|hidden)\b",
    r"\b(?:all\s+(?:of\s+)?(?:my|the|her|his)|a\s+whole\s+bottle\s+of|enough)\s+(?:sleeping\s+)?(?:pills|meds|painkillers|tylenol)\b",
    r"\b(?:got|have|found|took|grabbed|stole)\s+(?:the|some|a\s+bunch\s+of)\s+(?:sleeping\s+)?(?:pills|meds|painkillers)\s+from\b",
    # weapons / ligatures — not "a rope for the swing"
    r"\b(?:have|got|bought|buy|found|keep|hid|hidden|grabbed|sharpened)\s+(?:a|the|my|his|her|some)?\s*(?:gun|pistol|rifle|rope|noose|razor|razors|blade|blades)\b(?!\s+for\s+(?:the|a|my|our)\b)",
    r"\b(?:his|her|my\s+(?:dad|mom|parents|brother|stepdad)'?s?)\s+(?:gun|pistol|rifle|pills|meds)\b",
    r"\b(?:gun|pistol|rifle)\s+in\s+(?:the|his|her|my)\s+(?:closet|drawer|room|car|safe)\b",
    r"\bfrom\s+my\s+(?:mom|dad|parents)'?s?\s+(?:cabinet|medicine|room|drawer)\b",
)

# Physically at a place of danger right now.
_LOCATION = _rx(
    r"\b(?:standing|sitting|i'?m|im|i\s+am)\s+(?:on|at|by)\s+(?:the\s+)?(?:edge|ledge|bridge|roof|rooftop|tracks|train\s+tracks|cliff|overpass)\b",
)

# Goodbye / settling affairs. STRONG on its own = high; SOFT alone = low
# ("goodbye everyone" is usually just leaving the chat) but crisis after
# earlier risk in the same conversation.
_GOODBYE_STRONG = [re.compile(p, re.IGNORECASE) for p in (
    r"\b(?:this\s+is\s+)?my\s+last\s+(?:message|text|post|night|day|goodbye)\b",
    r"\b(?:wrote|writing|left)\s+(?:letters?|notes?|a\s+letter|a\s+note|everyone\s+(?:notes?|letters?))\b",
    r"\bnot\s+(?:their|your|anyone'?s)\s+fault\b",
    r"\b(?:giving|gave|give)\s+(?:my|all\s+my)\s+(?:stuff|things|clothes|games)\s+away\b|\bgiving\s+away\s+my\b|\bgiving\s+my\s+(?:stuff|things)\b",
    r"\bsaid\s+(?:my\s+)?goodbyes\b|\bsaid\s+goodbye\s+to\s+(?:my|everyone)\b",
    r"\btake\s+care\s+of\s+my\s+(?:dog|cat|sister|brother|mom|dad)\s+for\s+me\b",
)]
_GOODBYE = _rx(
    r"\bthank\s+you\s+for\s+(?:everything|being\s+my\s+friend|always\s+being)\b",
    r"\b(?:good\s*bye|goodbye|bye)\s+(?:every(?:one|body)|guys|world|forever)\b",
    r"\bgoodnight\s+every(?:one|body)\b|\bremember\s+me\b|\bat\s+peace\s+(?:now|with\s+it)\b",
)
_GOODBYE_INNOCENT = re.compile(
    r"\b(?:see\s+(?:you|ya|u)|ttyl|talk\s+tomorrow|until|till|later|monday|tmrw|tomorrow|after\s+(?:break|summer)|gotta\s+go|brb)\b",
    re.IGNORECASE)

# Self-harm / eating-disorder / medication behaviour.
_SELFHARM = _rx(
    r"\b(?:cutting|cut|sh|self\s*harm(?:ing|ed)?)\s+again\b",
    r"\b(?:cutting|cut|hurting|hurt|burning|burned|burnt|scratching|hitting|hit)\s+myself\s+(?:again|so\s+i|to\s+feel|every)\b",
    r"\b(?:been|started|keep|kept)\s+cutting\b(?!\s+(?:class|the|a|my\s+hair|back|down|corners|carbs|it|out|onions?))",
    r"\bmade\s+myself\s+(?:throw\s+up|puke|vomit|sick)\b|\bmake\s+myself\s+(?:throw\s+up|puke|vomit)\b",
    r"\bhaven'?t\s+eaten\s+(?:in|for)\s+(?:\w+\s+)?(?:days?|weeks?)\b|\bhaven'?t\s+eaten\s+since\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|yesterday|last\s+\w+)\b",
    r"\bnot\s+eaten\s+in\s+\w+\s+days\b|\bhavent\s+eaten\s+(?:in|for|since)\s+\w+\s*(?:days?|weeks?|monday|tuesday|wednesday|thursday|friday|yesterday)\b",
    r"\b(?:don'?t|dont|do\s+not)\s+deserve\s+(?:to\s+eat|food|to\s+be\s+happy|to\s+live|to\s+be\s+here)\b",
    r"\b(?:stopped|quit|not)\s+taking\s+my\s+(?:meds|medication|pills|antidepressants)\b",
    r"\brelaps(?:e|ed|ing)\b[^.?!]{0,20}\b(?:sh|self\s*harm|cutting)\b",
    r"\bso\s+i\s+could\s+feel\s+something\b",
)

# Abuse / not safe at home, threats with secrecy.
_ABUSE = _rx(
    r"\b(?:dad|mom|stepdad|step\s+dad|stepmom|father|mother|parents?|uncle|brother|boyfriend|bf|girlfriend|gf|he|she|they)\s+(?:hits|beats|chokes|kicks|slaps|hurts|touches|punches|hit|beat|choked|slapped|punched)\s+me\b",
    r"\b(?:scared|afraid|terrified)\s+to\s+go\s+home\b",
    r"\b(?:gets|is)\s+(?:so\s+)?(?:angry|violent|scary)\s+when\s+(?:he|she|they)\s+(?:drinks|drink|is\s+drunk|gets\s+drunk)\b",
    r"\bwhen\s+(?:he|she)'?s\s+drunk\b",
)
_THREAT_SECRECY = _rx(
    r"\bif\s+i\s+(?:tell|told|say|said)\s+any(?:one|body)\b[^.?!]{0,40}\b(?:kill|hurt|beat|end)\b",
    r"\b(?:he|she|they)(?:'ll|\s+will|\s+would|'d|\s+said\s+(?:he|she|they)(?:'d|'ll|\s+would|\s+will))\s+(?:kill|hurt|beat)\s+me\b[^.?!]{0,30}\bif\s+i\s+(?:tell|told)\b",
)

# Hopelessness / worthlessness / anhedonia / distress (moderate).
_HOPELESS = _rx(
    r"\b(?:don'?t|dont|do\s+not)\s+(?:want\s+to|wanna)\s+go\s+home\b(?!\s+(?:yet|now|early))",
    r"\bmake\s+it\s+(?:all\s+)?stop\b",
    r"\bno\s+way\s+(?:things|it|life|this)\s+(?:gets?|will\s+get|is\s+(?:gonna|going\s+to)\s+get|ever\s+gets?)\s+better\b",
    r"\bnothing\s+(?:ever\s+)?(?:gets|will\s+get|is\s+gonna\s+get)\s+better\b|\bnever\s+(?:gets|going\s+to\s+get|gonna\s+get)\s+better\b",
    r"\bwaste\s+of\s+(?:space|air|oxygen|time\s+as\s+a\s+person)\b|\b(?:i'?m|im|i\s+am)\s+(?:such\s+)?a\s+(?:waste|burden|failure|mistake|disappointment)\b",
    r"\b(?:a|the)\s+burden\s+(?:to|on|for)\b|\bfeel\s+like\s+a\s+burden\b",
    r"\b(?:tired\s+of|sick\s+of)\s+being\s+(?:the\s+problem|a\s+burden|a\s+disappointment|a\s+mistake)\b|\b(?:i'?m|im|i\s+am)\s+(?:always\s+)?the\s+problem\b",
    r"\b(?:don'?t|dont|do\s+not)\s+belong\b",
    r"\b(?:i\s+)?hate\s+(?:myself|being\s+me|who\s+i\s+am)\b|\bsick\s+of\s+being\s+me\b",
    r"\bdone\s+trying\b|\btired\s+of\s+trying\b|\bgave\s+up\s+on\s+(?:myself|everything|life)\b",
    r"\b(?:can'?t|cant|cannot)\s+keep\s+(?:pretending|doing\s+this|going\s+like\s+this)\b",
    r"\b(?:can'?t|cant|cannot)\s+do\s+this\s+anymore\b",
    r"\b(?:really|just|honestly)\s+not\s+(?:fine|okay|ok)\b|\bi'?m\s+not\s+(?:fine|okay|ok)\b|\bim\s+not\s+(?:fine|okay|ok)\b",
    r"\b(?:haven'?t|havent|don'?t|dont)\s+felt?\s+anything\s+in\b|\b(?:feel|felt)\s+(?:nothing|numb|empty)\b",
    r"\bnothing\s+makes\s+me\s+(?:happy|feel)\b|\bcan'?t\s+remember\s+the\s+last\s+time\s+i\s+(?:was|felt)\s+happy\b",
    r"\bmiss\s+(?:when|how)\s+i\s+used\s+to\s+(?:want|care|feel|enjoy|be\s+happy)\b",
    r"\b(?:what'?s|whats|what\s+is)\s+(?:even\s+)?the\s+point\b" + _EXISTENTIAL_ONLY,
    r"\b(?:life|everything|it\s+all|my\s+life)\s+(?:is|feels)\s+(?:so\s+)?(?:pointless|meaningless|empty|hopeless)\b",
    r"\b(?:nobody|no\s+one|noone)\s+(?:cares|loves\s+me|likes\s+me|would\s+care)\b(?!\s+about\s+(?!me\b))(?!\s+(?:what|how|who|that|if\s+(?:we|you|they|the))\b)",
    r"\b(?:don'?t|dont)\s+(?:even\s+)?care\s+(?:anymore|about\s+anything)\b",
    r"\b(?:panic\s+attacks?)\b|\b(?:can'?t|cant)\s+breathe\b",
    r"\b(?:drinking|drink|smoking|vaping)\s+(?:every\s+(?:night|day)|to\s+(?:fall\s+asleep|sleep|forget|numb|cope|feel))\b",
    r"\bit\s+(?:doesn'?t|doesnt)\s+matter\s+anymore\b|\bnothing\s+matters\b(?!\s+(?:more|as\s+much|but|except|to\s+(?:them|him|her)))",
    r"\bkeep\s+saying\s+i'?m\s+fine\b",
    r"\b(?:messing|mess|screw|screwing)\s+(?:everything|it\s+all)\s+up\b|\bi\s+(?:always\s+)?ruin\s+(?:things|everything)\b",
    r"\b(?:i'?m|im)\s+(?:such\s+)?(?:a\s+)?(?:waste|worthless|useless|pathetic)\b",
    r"\b(?:every(?:one|body))\s+hates\s+me\b|\bi'?m\s+(?:so\s+)?alone\b|\bim\s+(?:so\s+)?alone\b",
    r"\bcan'?t\s+stop\s+crying\b|\bcant\s+stop\s+crying\b",
    r"\b(?:the\s+|this\s+|my\s+)?(?:loneliness|depression|anxiety|sadness|emptiness|pain|feeling|thoughts|guilt)\s+(?:is|are)\s+(?:literally\s+|actually\s+|slowly\s+)?killing\s+me\b",
    r"\bso\s+tired\s+of\s+everything\b|\btired\s+of\s+everything\b",
)

# Weak / ambiguous distress (low): lean toward flagging, never alone above low.
_WEAK = _rx(
    r"\b(?:i'?m|im|i\s+am)\s+(?:so\s+)?done\s*(?:[.!?…]|$)",
    r"\bit\s+(?:doesn'?t|doesnt)\s+matter\b|\bwhatever\b[^.?!]{0,10}\bmatter\b",
    r"\b(?:no\s+one|nobody|noone)\s+(?:gets\s+it|understands)\b",
    r"\beverything\s+sucks\b|\bhate\s+it\s+here\b",
    r"\bjust\s+want\s+to\s+run\s+away\b|\bwanna\s+run\s+away\b",
    r"\bcan'?t\s+wait\s+for\s+(?:this|it)\s+(?:all\s+)?to\s+(?:all\s+)?be\s+over\b|\bcant\s+wait\s+for\s+(?:this|it)\s+(?:all\s+)?to\s+(?:all\s+)?be\s+over\b",
    r"\bi\s+just\s+want\s+it\s+(?:all\s+)?to\s+stop\b",
)
# A method named with first-person intent, even inside a joke ("lmao i'm gonna
# jump off the roof"): never erased, at least low.
_METHOD = _rx(
    r"\b(?:gonna|going\s+to|wanna|want\s+to|finna|about\s+to|might|will|i'?ll|ill)\s+(?:just\s+)?"
    r"(?:jump\s+off|jump\s+in\s+front\s+of|hang\s+myself|overdose|od|slit|drown\s+myself|"
    r"walk\s+into\s+traffic|throw\s+myself)\b",
)

# Timeline words only matter next to another risk signal.
_TIMELINE = re.compile(rf"\b{_TIME}\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# JOKE / intent markers
# ---------------------------------------------------------------------------
_LAUGH = re.compile(
    r"(?:\blo+l+\b|\blm(?:f?a+o+)\b|\bro+fl\b|\bha(?:ha)+h?\b|\bhehe+\b|\bjaja\w*\b"
    r"|😂|🤣|😹|💀|☠|\bjk\b|\bjus+t?\s+kidding\b|\bjoking\b|\bim\s+weak\b|\bcrying\s+laughing\b|\bkmsl\b)",
    re.IGNORECASE)
_WEAK_JOKE = re.compile(r"(?:😭|🙄|🤢|🤮|😩|😫|🥲|😤)")

# Something external and everyday that the "kill me" is about.
_REFERENT = re.compile(
    r"\b(?:test|tests|quiz|quizzes|exam|exams|final|finals|midterm\w*|homework|hw|class|classes|"
    r"period|teacher|essay|project|assignment|lab|chem|chemistry|calc|calculus|math|physics|bio|"
    r"biology|english|history|spanish|french|ap\s+\w+|sat|act|ted\s+talk|presentation|zoom|lecture|"
    r"grade|grades|report\s+card|semester|school|practice|coach|conditioning|game|match|ref|"
    r"tournament|lineup|team|season|wifi|phone|charger|song|playlist|movie|show|episode|meme|video|"
    r"cringe|recording|voice|lunch|cafeteria|food|pizza|bus|traffic|monday|mondays|group\s+project|"
    r"toothbrush|leftovers|hoodies?|screen\s+time|babysit\w*|text(?:ed|s)?\s+(?:me\s+)?back|"
    r"snow\s+day|spoil\w*|finale)\b",
    re.IGNORECASE)
_GAMING = re.compile(
    r"\b(?:among\s+us|sus|fortnite|valorant|minecraft|roblox|cod|warzone|apex|overwatch|league|"
    r"mario\s*kart|smash|2k|fifa|madden|ranked|lobby|1v1|squad|duos|game|gaming|playing|controller|"
    r"xbox|ps5|switch|discord)\b",
    re.IGNORECASE)
_HYPERBOLE_FRAME = _rx(
    # an inanimate / situational subject: "this homework is killing me" — not
    # "he's going to kill me", which is a threat
    r"\b(?:this|that|it|the\s+\w+|my\s+(?:homework|class|classes|schedule|job|back|head|feet|legs|brain)|"
    r"homework|school|work|practice|physics|chem|calc|math|bio|english|history|mondays?|"
    r"(?:this|that|the)\s+\w+\s+\w+)\s+(?:is|are|was|'s)\s+(?:actually\s+|literally\s+|lowkey\s+|trying\s+to\s+|gonna\s+|going\s+to\s+)?(?:killing|kill)\s+me\b",
    r"\b(?:the\s+)?(?:death|end)\s+of\s+me\b|\bgonna\s+end\s+me\b|\bgoing\s+to\s+end\s+me\b",
    r"\brather\s+die\s+than\b(?!\s+(?:keep\s+)?(?:living|live|going\s+on|go\s+on|being\s+alive|be\s+alive|being\s+here|be\s+here|being\s+me|wake\s+up|feel\s+like\s+this|feeling\s+like\s+this))|\bdead\s+man\b|\bscared\s+me\s+to\s+death\b|\bi'?m\s+deceased\b",
    r"\bput\s+me\s+out\s+of\s+my\s+misery\b",
    r"\bone\s+more\s+(?:time|ted|minute|second|day|class|word)\b|\bif\s+i\s+have\s+to\b",
    r"\b(?:could|can)\s+die\s+happy\b",
    r"\b(?:someone|somebody|pls|please|just)\s+end\s+me\b|^\W*end\s+me\W*$",
)
# Hyperbole that is a joke on its own, no external referent needed (still
# blocked by any real risk signal or earlier distress).
_HYPERBOLE_STRONG = _rx(
    r"\brather\s+die\s+than\b(?!\s+(?:keep\s+)?(?:living|live|going\s+on|go\s+on|being\s+alive|be\s+alive|being\s+here|be\s+here|being\s+me|wake\s+up|feel\s+like\s+this|feeling\s+like\s+this))|\bscared\s+me\s+to\s+death\b|\bi'?m\s+deceased\b|"
    r"\b(?:could|can)\s+die\s+happy\b|\bdie\s+(?:of|from)\s+(?:embarrassment|cringe|laughing)\b",
)
# "for real / not joking" — turns a joke reading off.
_SERIOUS_MARKER = re.compile(
    r"\b(?:not\s+(?:even\s+)?(?:joking|kidding|a\s+joke)|no\s+joke|for\s+real(?:\s+this\s+time)?|"
    r"i\s+mean\s+it|i'?m\s+serious|im\s+serious|being\s+serious|seriously\s+though|srsly|"
    r"actually\s+not|fr\s+fr|this\s+isn'?t\s+a\s+joke|deadass\s+(?:not|serious))\b",
    re.IGNORECASE)
# Retraction / deflection / minimisation — meaningful only after a disclosure.
_MINIMISE = re.compile(
    r"^(?:\W*(?:lol|lmao|haha\w*|jk|nvm|never\s*mind|kidding|just\s+kidding|anyway\w*|whatever|"
    r"it'?s?\s+(?:fine|ok|okay|nothing)|i'?m\s+(?:fine|ok|okay|good)(?:\s+now)?|im\s+(?:fine|ok|okay|good)(?:\s+now)?|"
    r"forget\s+(?:it|i\s+said\s+anything|what\s+i\s+said)|don'?t\s+worry(?:\s+about\s+it)?|dont\s+worry(?:\s+about\s+it)?|"
    r"don'?t\s+tell\s+any(?:one|body)|dont\s+tell\s+any(?:one|body)|i'?ll\s+be\s+(?:ok|okay|fine)|ill\s+be\s+(?:ok|okay|fine)|"
    r"i\s+guess|pls|please|now|haha|how\s+was\s+your\s+day|nothing|idk)\W*)+$"
    r"|\b(?:jk|nvm|never\s*mind|forget\s+i\s+said\s+anything|don'?t\s+tell\s+any(?:one|body)|dont\s+tell\s+any(?:one|body)|"
    r"don'?t\s+worry\s+about\s+(?:it|me)|dont\s+worry\s+about\s+(?:it|me)|anyway\s+how|i'?m\s+fine\s+now|im\s+fine\s+now|"
    r"i'?ll\s+be\s+(?:ok|okay|fine)|ill\s+be\s+(?:ok|okay|fine)|it'?s\s+fine)\b",
    re.IGNORECASE)
# Short continuation words that carry the previous message's meaning.
_CONTINUATION_TIME = re.compile(rf"^\W*(?:{_TIME}|soon|i'?m\s+ready|im\s+ready|it'?s\s+time)\W*$", re.IGNORECASE)
_TIRED = re.compile(r"\b(?:tired|exhausted|drained|done|over\s+it|empty|numb|cant\s+anymore|can'?t\s+anymore)\b", re.IGNORECASE)
_FICTION_OR_META = re.compile(
    r"\b(?:the\s+character|in\s+the\s+(?:book|movie|show|game|song)|the\s+(?:book|movie|show)\s+where|"
    r"suicide\s+prevention|awareness\s+(?:week|month|assembly)|assembly|essay\s+(?:on|about)|"
    r"research\s+paper|for\s+(?:health|psych)\s+class)\b",
    re.IGNORECASE)

# Harm aimed at, or reported about, another person.
_OTHER_TARGET = re.compile(
    r"\b(?:him|her|them|you|u|ya|that\s+guy|this\s+guy|their|his|someone|everyone|teacher|"
    r"boss|ex|bully|classmate|himself|herself|themselves)\b", re.IGNORECASE)
_REPORTED = re.compile(
    r"\b(?:friend|classmate|sister|brother|cousin|bf|gf|boyfriend|girlfriend|roommate|he|she|they)"
    r"\s+(?:said|says|told\s+me|keeps\s+saying|posted|texted|wants|is\s+going)\b", re.IGNORECASE)

STRONG_RISKS = ("ideation", "plan", "means", "location", "selfharm", "abuse", "threat_secrecy")


def analyze(text: str) -> Dict[str, Any]:
    """Risk and joke signals for ONE message (already lowercased/normalised)."""
    t = text or ""
    risk: Dict[str, int] = {}

    def hit(name: str, rx: "re.Pattern", level: int) -> None:
        if rx.search(t):
            risk[name] = max(risk.get(name, 0), level)

    hit("ideation", _IDEATION, 3)
    hit("plan", _PLAN, 3)
    hit("means", _MEANS, 3)
    hit("location", _LOCATION, 4)
    strong_bye = sum(1 for rx in _GOODBYE_STRONG if rx.search(t))
    if strong_bye:
        risk["goodbye"] = 4 if strong_bye >= 2 else 3
    elif _GOODBYE.search(t) and not _GOODBYE_INNOCENT.search(t):
        risk["goodbye_soft"] = 1
    hit("explicit", _EXPLICIT, 4)
    hit("selfharm", _SELFHARM, 3)
    hit("abuse", _ABUSE, 3)
    hit("threat_secrecy", _THREAT_SECRECY, 4)
    hit("hopeless", _HOPELESS, 2)
    hit("weak", _WEAK, 1)
    hit("method_mention", _METHOD, 1)

    # A plan with nothing self-directed in it ("i already decided on a college",
    # "looked up how to make pancakes") is not risk on its own.
    if "plan" in risk and not re.search(
            r"\b(?:do\s+it|end|die|kill|over|it|pills?|take|friday|tonight|tomorrow|night|after\s+school)\b",
            t[_PLAN.search(t).start():], re.IGNORECASE):
        risk.pop("plan")

    timeline = bool(_TIMELINE.search(t))
    strong = [k for k in STRONG_RISKS if k in risk]
    if timeline and (strong or "goodbye" in risk):
        risk["timeline"] = 4
    if len(set(strong) | ({"goodbye"} if "goodbye" in risk else set())) >= 2:
        risk["combined"] = 4
    if "plan" in risk and ("means" in risk or "ideation" in risk):
        risk["combined"] = 4
    # A decision + a date with nothing else: high, not crisis ("i already decided. friday after school.")
    if "plan" in risk and timeline:
        risk["plan"] = max(risk["plan"], 3)

    fiction = bool(_FICTION_OR_META.search(t))
    return {
        "risk": risk,
        "laugh": bool(_LAUGH.search(t)),
        "weak_joke": bool(_WEAK_JOKE.search(t)),
        "referent": bool(_REFERENT.search(t)),
        "gaming": bool(_GAMING.search(t)),
        "hyperbole_frame": bool(_HYPERBOLE_FRAME.search(t)),
        "hyperbole_strong": bool(_HYPERBOLE_STRONG.search(t)),
        "serious_marker": bool(_SERIOUS_MARKER.search(t)),
        "minimise": bool(_MINIMISE.search(t.strip())),
        "continuation_time": bool(_CONTINUATION_TIME.search(t.strip())),
        "tired": bool(_TIRED.search(t)),
        "timeline": timeline,
        "fiction": fiction,
        "plan_words": bool(_PLAN.search(t)),
        "words": len(re.findall(r"[a-z']+", t)),
    }


def risk_level(sig: Dict[str, Any]) -> int:
    return max(sig["risk"].values(), default=0)


def blocking_risks(sig: Dict[str, Any]) -> List[str]:
    """Risk signals strong enough that a joke marker may NOT lower anything."""
    return [k for k, v in sig["risk"].items() if v >= 2]


# ---------------------------------------------------------------------------
# Decision: floor / cap for the current message given its history
# ---------------------------------------------------------------------------

def assess(sig: Dict[str, Any], base: Dict[str, Any], history: Iterable[Dict[str, Any]] = (),
           joined: Optional[Dict[str, Any]] = None, text: str = "") -> Dict[str, Any]:
    """Combine this message's signals with Layer-1's raw result and the
    conversation so far.

    sig      analyze() of the current message
    base     layer1's raw (keyword-only) result for the current message
    history  for each earlier STUDENT message, oldest first:
             {"level": final level, "raw_level": keyword level before any joke
              cap, "sig": analyze(...), "joke_capped": bool}
    joined   analyze() of the last few messages + this one run together, for
             thoughts split across several texts ("i'm so tired" / "of everything")

    Returns {"floor", "cap", "reasons", "risk_signals", "joke_markers",
             "history_signals"}; layer1 applies level = min(max(level, floor), cap).
    """
    history = list(history)
    reasons: List[str] = []
    floor = risk_level(sig)
    if floor:
        reasons.append(f"risk:{'+'.join(sorted(sig['risk']))}")
    risks = blocking_risks(sig)

    # ---- conversation context ----------------------------------------------
    hist_sigs = [h["sig"] for h in history]
    hist_ideation = any(
        (h["level"] >= 3 and not h.get("joke_capped"))
        or any(k in h["sig"]["risk"] for k in STRONG_RISKS + ("goodbye",))
        for h in history)
    hist_distress = sum(1 for h in history if h["level"] >= 2 or risk_level(h["sig"]) >= 2)
    hist_selfharm_joke = max((h["raw_level"] for h in history if h.get("joke_capped")), default=0)
    recent = hist_sigs[-2:]
    hist_referent = any(s["referent"] or s["gaming"] for s in recent)
    hist_gaming = any(s["gaming"] for s in recent)
    hist_signals: List[str] = []

    if hist_ideation:
        hist_signals.append("earlier_ideation")
        if sig["continuation_time"] or sig["risk"].get("plan") or sig.get("plan_words") \
                or sig["risk"].get("goodbye") \
                or sig["timeline"] and sig["words"] <= 4:
            floor = max(floor, 4); hist_signals.append("plan_or_time_after_ideation")
        elif sig["minimise"] or sig["laugh"] or sig["weak_joke"]:
            floor = max(floor, 3); hist_signals.append("retraction_after_disclosure")
        elif risk_level(sig) >= 1 or sig["tired"] or base["level"] >= 1:
            floor = max(floor, 3); hist_signals.append("continued_distress")
        elif sig["words"] <= 6:
            floor = max(floor, 2); hist_signals.append("short_reply_in_risk_conversation")
    if hist_distress >= 1 and (risk_level(sig) >= 1 or sig["tired"] or base["level"] >= 1):
        lvl = 3 if hist_distress >= 2 else 2
        floor = max(floor, lvl); hist_signals.append(f"repeated_distress_x{hist_distress + 1}")
    if hist_distress >= 1 and sig["minimise"]:
        floor = max(floor, 2); hist_signals.append("minimising_after_distress")
    # Hopelessness on top of earlier distress = escalating, not a one-off vent.
    hist_risk2 = sum(1 for s in hist_sigs if risk_level(s) >= 2)
    if sig["risk"].get("hopeless") and (hist_risk2 >= 1 or hist_distress >= 1):
        floor = max(floor, 3); hist_signals.append("hopelessness_after_distress")
    if sig["serious_marker"] and (hist_selfharm_joke or hist_distress or hist_ideation):
        floor = max(floor, hist_selfharm_joke or 2, 3 if hist_selfharm_joke else 2)
        hist_signals.append("unjoking_earlier_message")
    if joined is not None:
        jl = risk_level(joined)
        prev_max = max([risk_level(s) for s in hist_sigs] + [risk_level(sig)], default=0)
        if jl > prev_max:
            floor = max(floor, jl); hist_signals.append(f"split_message:{'+'.join(sorted(joined['risk']))}")
            risks = risks + [k for k, v in joined["risk"].items() if v >= 2]
    if hist_signals:
        reasons.append("history:" + ",".join(hist_signals))

    # ---- joke handling --------------------------------------------------------
    cap = None
    joke_markers: List[str] = []
    for name in ("laugh", "weak_joke", "referent", "gaming", "hyperbole_frame", "fiction"):
        if sig[name]:
            joke_markers.append(name)
    if not sig["referent"] and not sig["gaming"] and hist_referent and not hist_ideation:
        joke_markers.append("history_referent")

    blocked = bool(risks) or sig["serious_marker"] or hist_ideation or hist_distress >= 1
    # Computed even when no keyword matched: Layer 1 applies it to its keyword
    # level, and detection.py uses it as a ceiling on the model's verdict.
    if not blocked:
        external = sig["referent"] or sig["gaming"] or sig["hyperbole_frame"] or \
            (hist_referent and sig["words"] <= 8)
        gaming = sig["gaming"] or hist_gaming
        other_directed = bool(base.get("received_threat")) or any(
            _OTHER_TARGET.search(h["phrase"]) for h in base.get("hits", [])) or bool(_REPORTED.search(text))
        if gaming and other_directed:
            cap = 1; reasons.append("joke:game_trash_talk")
        elif other_directed:
            # Violence toward a real person (a teacher, a classmate) is never
            # waved off by an emoji. A clear laugh marker only lowers it to
            # moderate so it still surfaces.
            if sig["laugh"]:
                cap = 2; reasons.append("joke:laugh_but_aimed_at_a_person")
        elif sig["fiction"]:
            cap = 1; reasons.append("joke:fiction_or_meta")
        elif (sig["laugh"] or sig["weak_joke"]) and external:
            cap = 1; reasons.append("joke:hyperbole_about_something_external")
        elif sig["hyperbole_frame"] and (sig["referent"] or (hist_referent and sig["words"] <= 8)):
            cap = 1; reasons.append("joke:hyperbole_frame")
        elif sig.get("hyperbole_strong"):
            cap = 1; reasons.append("joke:hyperbole_idiom")
    # Rule 2: an explicit self-harm term is never erased, only lowered.
    if base.get("always_serious"):
        floor = max(floor, 1)
    if cap is not None and cap < floor:
        cap = floor
    return {
        "floor": floor, "cap": cap, "reasons": reasons,
        "risk_signals": sorted(sig["risk"]),
        "joke_markers": joke_markers,
        "history_signals": hist_signals,
    }


# ---------------------------------------------------------------------------
# Conversation history from the live chat request (no app.py change needed)
# ---------------------------------------------------------------------------

def request_history(max_messages: int = 8) -> List[str]:
    """Earlier STUDENT messages of the conversation being classified, when
    called inside the Coping Chat request (POST /api/chat sends the prior turns
    as `messages`). Returns [] anywhere else (monitor/scan/classify endpoints,
    tests, scripts), so it can never mix one conversation into another.

    This lets detection use context without touching app.py. Callers that
    have the history should pass it explicitly instead.
    """
    try:
        from flask import has_request_context, request
    except ImportError:
        return []
    try:
        if not has_request_context() or request.path != "/api/chat":
            return []
        data = request.get_json(silent=True) or {}
        msgs = data.get("messages") or []
        out = [str(m.get("content", ""))[:500] for m in msgs
               if isinstance(m, dict) and m.get("role") == "user" and m.get("content")]
        return out[-max_messages:]
    except Exception:  # never let context lookup break detection
        return []
