# Setup — about 20 minutes, all free

You do this once. After that you never touch it again; you just open the
dashboard on your phone.

Steps 1–4 get it running. Steps 5–6 add phone notifications and better data.
If you only do steps 1–4, everything still works.

---

## Step 1 — Make a GitHub account (3 min)

Go to **github.com** → Sign up. Free plan. That's it.

*(What this is for: GitHub stores the portfolio files, runs the trading script
on a timer using their computers so yours can be off, and publishes the
dashboard to a web address. You won't use GitHub day to day.)*

---

## Step 2 — Create the repository (2 min)

1. Click the **+** in the top-right → **New repository**
2. Repository name: **`portfolio-desk`**
3. Choose **Public** (GitHub Pages needs a paid plan on private repos).
   Nothing sensitive lives in this repo - no keys, no personal data, and the
   ntfy topic is stored as an encrypted Secret, never as a file.
4. Do **not** check "Add a README file"
5. Click **Create repository**

---

## Step 3 — Upload the files (3 min)

On the empty repo page, click **uploading an existing file**.

Unzip `portfolio-desk.zip` on your computer, then drag **everything inside it**
into the browser window — all the files and folders at once.

> **Important:** drag the *contents* of the unzipped folder, not the folder
> itself. You should see `engine`, `state`, `docs`, `.github`, `IPS.md`, and the
> rest land in the list.

Scroll down, click **Commit changes**.

**Check it worked:** you should see a folder called `.github` in the file list.
If you don't, the upload missed the hidden folder — see Troubleshooting below.

---

## Step 4 — Turn on the dashboard website (2 min)

1. In your repo, click **Settings** (top bar)
2. Left sidebar → **Pages**
3. Under "Build and deployment" → Source: **Deploy from a branch**
4. Branch: **`main`**, folder: **`/docs`** → click **Save**
5. Wait about a minute, then refresh the page. GitHub shows your address:

```
https://YOUR-USERNAME.github.io/portfolio-desk/
```

**Open that on your phone and add it to your home screen.** On iPhone: Share
button → Add to Home Screen. It now behaves like an app.

Then go to the **Actions** tab → click **Daily mark & publish** → **Run
workflow** to populate it for the first time. After this it runs by itself every
weekday just after the market closes.

---

## Step 5 — Phone notifications (5 min, optional but you asked for it)

1. Install the **ntfy** app (free — App Store or Google Play)
2. Open it, tap **+**, and subscribe to this exact topic:

```
<the topic Claude gives you in conversation>
```

**The topic name is a password.** Anyone who knows it can read your trade alerts
and send you fake ones. It is deliberately NOT written in this file or anywhere
else in this repository — if the repo is ever public, its git history is public
too, and a secret committed even once is compromised permanently. It lives only
in GitHub's encrypted Secrets store.

3. Back in GitHub: **Settings → Secrets and variables → Actions**
4. Click **New repository secret**
   - Name: `NTFY_TOPIC`
   - Secret: the topic name from step 2
   - **Add secret**
5. Click the **Variables** tab → **New repository variable**
   - Name: `DASHBOARD_URL`
   - Value: your Pages address from step 4
   - *(This makes trade notifications tappable — they open the dashboard.)*

You'll now get a push on every trade, and nothing else.

---

## Step 6 — Better market data (5 min, optional)

Works without this — the default source needs no key. These add fallbacks so a
single provider outage can't stall the marks.

**Finnhub** (60 calls/min free): sign up at finnhub.io → copy your API key →
add as a repository secret named `FINNHUB_KEY`.

**Alpha Vantage** (5 calls/min free): claim a key at alphavantage.co →
add as a repository secret named `ALPHAVANTAGE_KEY`.

---

## That's it

From here:

- **The dashboard** updates itself every weekday after the close.
- **Notifications** arrive only when a trade actually happens.
- **Every trade** is a commit in the repo — tap any commit to see exactly what
  changed and why. I cannot rewrite that history without you being able to see it.

---

## Running it on your own computer instead

Not required, but useful if you want to watch it work:

```bash
cd portfolio-desk
python3 -m engine.run selftest    # which data sources are alive right now
python3 -m engine.run daily       # mark, apply rules, rebuild the dashboard
open docs/index.html              # (Linux: xdg-open, Windows: start)
```

Run the test suite any time you change something:

```bash
python3 -m tests.test_offline     # 49 checks, no network needed
```

---

## Troubleshooting

**The Actions tab shows a red X.** Click the failed run to see the log. The most
common cause is a data source being down that day — the run refuses to write
made-up prices and exits, which is intended. It'll pick up on the next run.

**The `.github` folder didn't upload.** Some browsers skip dotted folders when
you drag them. Fix: in your repo, click **Add file → Create new file**, type
`.github/workflows/daily.yml` as the name (typing the slashes creates the
folders), paste the contents of that file from the zip, commit. Repeat for
`.github/workflows/execute.yml`.

**Dashboard says "No data yet."** The daily workflow hasn't run. Actions tab →
Daily mark & publish → Run workflow.

**Dashboard shows old numbers.** GitHub Pages caches for a few minutes. Pull to
refresh, or hard-refresh the page.

**Notifications aren't arriving.** Check that the `NTFY_TOPIC` secret exactly
matches what you subscribed to in the app — no spaces, no capitals. Also note
you'll only get one when a trade actually fills, which is roughly twice a month
per portfolio by design.
