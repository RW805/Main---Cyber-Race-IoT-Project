"""
Cybersecurity True/False question bank.

Written for players aged 8-18: short statements in plain language, no jargon,
about things young people actually come across online -- passwords, scams,
strangers, downloads, sharing, and getting help.

Each question is a dict:
    text     -> the statement shown to the player (keep it short and simple)
    answer   -> True or False (the correct answer)
    explain  -> short one-line explanation shown after answering (learning value)

Extend this list freely -- it's the easiest part of the project to grow.
Run `python3 questions.py` afterwards: it checks every question is short enough
and that there's a fair mix of True and False answers.
"""
import random

MAX_TEXT = 72      # characters -- keeps every question to one or two short lines
MAX_EXPLAIN = 80

QUESTIONS = [
    # --- Passwords ---
    {"text": "A good password is long and hard to guess.",
     "answer": True,
     "explain": "Long passwords are much harder for hackers to crack."},
    {"text": "'password123' is a strong password.",
     "answer": False,
     "explain": "It's one of the first passwords hackers try!"},
    {"text": "It's fine to share your password with your best friend.",
     "answer": False,
     "explain": "Keep passwords to yourself (and a parent or carer)."},
    {"text": "Your pet's name and birthday make a strong password.",
     "answer": False,
     "explain": "Things people know about you are easy to guess."},
    {"text": "Using a different password for each account is a good idea.",
     "answer": True,
     "explain": "If one gets stolen, your other accounts stay safe."},
    {"text": "A code sent to your phone when you log in makes an account safer.",
     "answer": True,
     "explain": "Even if someone guesses your password, they still need the code."},
    {"text": "You should log out when you use a shared or school computer.",
     "answer": True,
     "explain": "Otherwise the next person could get into your account."},

    # --- Scams and tricks ---
    {"text": "A message saying 'You've won a prize! Click here!' could be a scam.",
     "answer": True,
     "explain": "If it sounds too good to be true, it probably is."},
    {"text": "You should click links in messages from people you don't know.",
     "answer": False,
     "explain": "Unknown links can lead to scams or viruses."},
    {"text": "Phishing is when someone tricks you into giving away your details.",
     "answer": True,
     "explain": "Like fishing, they use bait to try to hook you!"},
    {"text": "Hackers can send messages pretending to be someone you know.",
     "answer": True,
     "explain": "Fake messages can look like they're from a friend. Check first!"},
    {"text": "If a website looks real, it must be safe.",
     "answer": False,
     "explain": "Fake sites can copy the real look. Check the web address."},
    {"text": "Pop-ups saying 'Your device has a virus!' are often fake.",
     "answer": True,
     "explain": "Close them. Don't click them or call any number they show."},
    {"text": "Hackers only go after big companies, not normal people.",
     "answer": False,
     "explain": "Anyone can be a target, so everyone needs to stay safe."},

    # --- Strangers and sharing ---
    {"text": "Everyone online is who they say they are.",
     "answer": False,
     "explain": "People can easily pretend to be someone else online."},
    {"text": "It's safe to tell people online your home address.",
     "answer": False,
     "explain": "Keep personal info like your address and school private."},
    {"text": "It's OK to accept friend requests from people you've never met.",
     "answer": False,
     "explain": "Only add people you know in real life."},
    {"text": "Anything you post online could stay there forever.",
     "answer": True,
     "explain": "Even deleted posts can be screenshotted or saved."},
    {"text": "Showing your location to everyone on social media is safe.",
     "answer": False,
     "explain": "Strangers could find out where you are. Keep it to people you trust."},

    # --- Getting help ---
    {"text": "You should tell a trusted adult if something online upsets you.",
     "answer": True,
     "explain": "Talking to someone you trust is always the right move."},
    {"text": "If someone is bullying you online, you should keep it a secret.",
     "answer": False,
     "explain": "Tell a trusted adult. You don't have to deal with it alone."},

    # --- Devices, downloads and viruses ---
    {"text": "Updating your apps and games helps keep them safe.",
     "answer": True,
     "explain": "Updates often fix holes that hackers could use."},
    {"text": "Turning off updates makes your device safer.",
     "answer": False,
     "explain": "Updates fix security problems, so keep them switched on."},
    {"text": "Free games from random websites can have viruses hidden in them.",
     "answer": True,
     "explain": "Stick to official app stores you can trust."},
    {"text": "It's safe to plug in a USB stick you found on the ground.",
     "answer": False,
     "explain": "It could have a virus on it. Hand it in instead."},
    {"text": "Antivirus software helps protect your computer from viruses.",
     "answer": True,
     "explain": "It looks for harmful programs and blocks them."},
    {"text": "If you have antivirus, you can never get a virus.",
     "answer": False,
     "explain": "It helps a lot, but you still need to be careful what you click."},
    {"text": "Free public Wi-Fi, like in a cafe, is always totally safe.",
     "answer": False,
     "explain": "Others might see what you do. Don't log in to important things."},
    {"text": "Backing up your files means keeping a spare copy of them.",
     "answer": True,
     "explain": "If something goes wrong, you won't lose your work."},
    {"text": "A virus is a program that can harm your computer.",
     "answer": True,
     "explain": "Viruses can delete files, slow things down or spy on you."},
]


class QuestionDeck:
    """Serves questions without repeating one until the deck is exhausted, then reshuffles."""

    def __init__(self, pool=None, seed=None):
        self.pool = list(pool if pool is not None else QUESTIONS)
        self._rng = random.Random(seed)
        self._deck = []

    def next_question(self):
        if not self._deck:
            self._deck = self.pool[:]
            self._rng.shuffle(self._deck)
        return self._deck.pop()


if __name__ == "__main__":
    # quick sanity check
    deck = QuestionDeck(seed=1)
    seen = [deck.next_question()["text"] for _ in range(len(QUESTIONS))]
    assert len(set(seen)) == len(QUESTIONS), "deck should not repeat before exhausting pool"

    # every question is short and simple enough for the 8-18 audience
    for q in QUESTIONS:
        assert set(q) == {"text", "answer", "explain"}, q
        assert isinstance(q["answer"], bool), q
        assert len(q["text"]) <= MAX_TEXT, f"question too long ({len(q['text'])} chars): {q['text']}"
        assert len(q["explain"]) <= MAX_EXPLAIN, f"explanation too long: {q['explain']}"
    texts = [q["text"] for q in QUESTIONS]
    assert len(set(texts)) == len(texts), "duplicate question"

    # a fair mix, so always pressing T (or F) doesn't win
    trues = sum(q["answer"] for q in QUESTIONS)
    assert abs(trues - (len(QUESTIONS) - trues)) <= 2, f"{trues} True vs {len(QUESTIONS) - trues} False"
    longest = max(len(t) for t in texts)
    print(f"OK: {len(QUESTIONS)} questions ({trues} True / {len(QUESTIONS) - trues} False), "
          f"longest {longest} chars, deck cycles without repeats.")
