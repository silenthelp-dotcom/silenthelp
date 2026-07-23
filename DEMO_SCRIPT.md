# SilentHelp — Demo Video Production Script

A complete shot list, narration, and record path for a ~90-second cinematic
product demo. Shoot each scene by screen-recording the live app at
`https://silenthelp.onrender.com` (or the self-running page at `/demo`, which
drives the flows automatically — see the end of this file).

**Format:** 1920×1080, 30fps. Record at 2× device pixel ratio if possible for
crisp text. Dark UI, so keep room lights low when filming a real Mac.

**Music:** slow ambient / piano, ~70 BPM. Nothing with lyrics. The product is
about quiet, so let the visuals breathe — long holds, slow pushes.

---

## COLD OPEN · 0:00–0:08 · "the moment before"

**Shot:** Real hands typing on a phone in Messages (or the Mac agent watching a
text field). Shallow depth of field, screen glowing in a dark room. The person
types something heavy — *"i don't even know why i'm still trying"* — then pauses,
thumb hovering, and deletes it.

**On-screen text (fades in, Instrument Serif italic):**
> Some things never get said out loud.

**VO:** *"Most people don't reach out when they're struggling. They go quiet."*

**Cut on:** the deleted message, cursor blinking on an empty field.

---

## SCENE 1 · 0:08–0:20 · Detection, on-device

**Shot:** Screen-record the Mac. Same text field. This time they leave the
sentence in. Cut to a tight shot of the SilentHelp menu-bar icon going from
grey to a soft pulse. A native popup slides in from the top-right — *not* a
browser, the real agent.

**On-screen text:**
> Detected on your Mac. In under a millisecond. Nothing sent anywhere.

**VO:** *"SilentHelp reads the rhythm of your own device — never your diary —
and notices the moment something's wrong."*

**Record path (self-running demo covers this):**
`/demo?scene=detection` — types the message, fires the popup.

---

## SCENE 2 · 0:20–0:36 · The four layers

**Shot:** Cut to the landing page `#science` / `#how` section. Slow scroll down
the four-layer list. Push in on each as the VO names it. The Lithos rock behind
"Support that notices first" reveals under the cursor spotlight — move the
cursor slowly so the moss-and-flowers layer blooms through.

**On-screen text (each appears as its layer is named):**
> Keyword · Semantic · Behavioral · Trend

**VO:** *"Four quiet layers. Keywords catch the obvious. A model reads the
meaning behind a joke. Behavior tracks your rhythm without reading a word. And
nothing surfaces until a real pattern forms."*

---

## SCENE 3 · 0:36–0:50 · The dashboard

**Shot:** Open `/app` → Dashboard. Slow hold on the Mental Battery — the
iridescent orb behind the number, the reading rows, the "what the surface shows"
insight. Let the orb's light move. Push in gently on the battery number.

**On-screen text:**
> Your focus, energy, and burnout — before you'd think to ask.

**VO:** *"It surfaces your focus, your energy, your burnout risk — as care, not
an alarm."*

**Record path:** `/demo?scene=dashboard`

---

## SCENE 4 · 0:50–1:04 · Help a Friend

**Shot:** Open `/app` → Help a Friend (coach mode). Type a friend's message into
the box — *"my friend keeps saying everyone would be better off without them"* —
and show SilentHelp coaching the user on how to respond: what to say, what not
to, when to escalate. Hold on the guidance.

**On-screen text:**
> When it's someone else who's struggling.

**VO:** *"And when it's a friend who's slipping, SilentHelp helps you find the
words — and know when it's time to bring in a real person."*

**Record path:** `/demo?scene=helper`

---

## SCENE 5 · 1:04–1:18 · Escalation — the human hand-off

**Shot:** Trigger the urgent moment (`/app`, sidebar → "Something surfacing").
The full-screen escalation: "Something important is surfacing." Show the drafted
counselor note. Cursor moves to **Send** — hold, don't click yet.

**On-screen text:**
> You're always the one who presses send.

**VO:** *"When it truly matters, it drafts the message to someone who can help.
You read it. You send it. You're always in control."*

*(NOTE: if the auto-send-on-repeated-crisis behavior is enabled, change this
line — see the open question in the project. As written, this reflects the
"user presses send" promise on the privacy page.)*

---

## SCENE 6 · 1:18–1:28 · Landing + close

**Shot:** Cut to the landing page hero — the video orb, "See beneath the
surface" in Instrument Serif. Slow push in. End on the badge logo, centered,
black background.

**On-screen text:**
> SilentHelp
> Support that notices before you ask.
> Free for students · On your Mac · Private by design

**VO:** *"SilentHelp. Support that notices — before you ask."*

**Final frame:** logo + `silenthelp.org` (once the domain is connected).

---

## SHOT DISCIPLINE (what makes it cinematic, not a screen recording)

- **Slow everything down.** Move the cursor at half speed. Let each screen hold
  for 2–3 seconds before cutting. No fast scrolling.
- **Push-ins.** A slow zoom (even 105%→100% in post) on the battery orb, the
  popup, the drafted note — gives static UI life.
- **Match cuts on motion.** Cut from the phone-deleting-a-message to the Mac
  detecting it — same gesture, different device.
- **Negative space.** The UI is mostly black. Don't fill it. Let text sit alone.
- **One accent color.** Everything is white-on-black; the only warmth is the
  video orb. Keep it that way in grade.

## CRISIS-CONTENT CARE

This demo shows self-harm language ("everyone would be better off without
them"). If it's going anywhere public:
- Add a card at the end: **"If you're struggling, call or text 988."**
- Don't linger on the crisis phrasing — show the *response*, not the distress.
- Consider a content note at the start.

## RECORDING CHECKLIST

- [ ] Backend awake (Render free tier sleeps — hit the URL once first)
- [ ] Signed in with a clean demo account (name shows in greeting)
- [ ] `popup_policy` set so moments actually surface
- [ ] Menu-bar agent running if filming native popups
- [ ] Screen recorder at 1920×1080, 30fps, no notifications/other apps visible
- [ ] `/demo` page tested — see below
