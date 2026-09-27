# Trending Topic Finder — 5 Channels (Telegram + GitHub, No Paid API)

## Ye kya karta hai
- 5 channels (sg-news-automation, tech-review-bot, bg-auto-job-bot,
  history-facts-bot, reels-bot) ke liye har din trending topics dhoondta hai
- YouTube (yt-dlp), Reddit (public JSON), Google Trends (unofficial endpoint) —
  teeno se mila kar list banata hai
- Duplicate topics repeat nahi hote (history.json track karta hai)
- Har topic ko score deta hai (views/recency + optional Gemini AI scoring)
- Telegram par ✅ Use / ❌ Skip buttons ke saath list bhejta hai
- Competitor channels ke naye videos par alert
- Purani uploaded videos ke views track karke batata hai kaunsi category
  best chal rahi hai
- Ek hi tareeke se chalega: roz subah automatic 6:00 AM IST par list Telegram par aa jayegi

## Setup Steps

1. **Naya GitHub repo banao** (ya kisi existing repo mein ye files daal do)
   aur is folder ka pura content usme daal do.

2. **Telegram Bot banao** (agar nahi hai):
   - @BotFather ko Telegram par message karo -> `/newbot` -> token milega

3. **Apna chat_id pata karo**:
   - Bot ko ek message bhejo, fir browser mein kholo:
     `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - `"chat":{"id": ...}` wahan chat_id milega

4. **GitHub repo Settings -> Secrets and variables -> Actions** mein add karo:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GEMINI_API_KEY` (optional — na do to bhi chal jayega, sirf AI scoring
     skip ho jayegi)

5. **Competitor channels add karna ho** (optional): `trending_finder.py`
   mein har channel ke `"competitors": []` list mein YouTube channel URL
   daal do, jaise:
   `"competitors": ["https://www.youtube.com/@SomeCompetitorChannel"]`

6. Bas — commit + push karte hi workflow apne aap active ho jayega:
   - `daily-auto-run.yml` — roz subah THEEK 6:00 AM IST par automatic list Telegram par aayegi

## Repo cleanup (agar pehle wala version already push kiya hai)
Agar aapne pehle `trending-finder.yml` workflow file aur `telegram_listener.py`
already apne repo mein daal diya hai, to unhe repo se **delete** kar dein —
warna wo har 5 minute chalte rahenge. Sirf `daily-auto-run.yml` aur
`trending_finder.py` rakhne hain.

## Manual test
GitHub repo ke "Actions" tab mein jaake "Daily Auto Trending Run" workflow
open karo aur "Run workflow" dabao — turant test ho jayega.

## Limitation (dhyaan rakhna)
- yt-dlp aur Google Trends dono unofficial/scraping-based hain, kabhi-kabhi
  format badalne par error aa sakta hai — code try/except ke saath likha
  hai taaki ek source fail ho to baaki chalte rahein
- Auto-Pipeline (topic -> seedha video banana -> upload) is version mein
  **shaamil nahi hai** — jab chahiye ho tab bata dena, alag se jod denge
