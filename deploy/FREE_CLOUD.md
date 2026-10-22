# Free deployment: Supabase + Firebase Hosting (no card)

The fog layer runs on your laptop. The cloud tier is free and needs no credit card.

```
Laptop (edge + fog)                                Cloud (free tier, no card)
┌───────────────────────────────────┐   HTTPS    ┌──────────────────────────────┐
│ Bin simulator -> fog nodes        │  upsert    │ Supabase (Postgres)          │
│ (routing, gossip, election,       │ ─────────▶ │ table `snapshots`, row 'live'│
│  ledger) + FastAPI on :8000       │ every 3 s  │ RLS: public read-only        │
│ web/cloud_publisher.py            │            └──────────────┬───────────────┘
└───────────────────────────────────┘                           │ read (publishable key)
                                                   ┌────────────▼───────────────┐
             Anyone's browser  ◀──────────────────│ Firebase Hosting            │
                                                   │ read-only dashboard         │
                                                   └────────────────────────────┘
```

| Tool | Role |
|---|---|
| FastAPI | Fog layer API and local admin dashboard |
| Supabase | Cloud data store that receives fog snapshots |
| Firebase Hosting | Public, read-only dashboard |
| Postman | Tests both the local API and the Supabase API |

**What to say in the viva:** the edge and fog layers (bins, fog nodes, routing,
election, gossip, ledger) run on one laptop, with the fog nodes as threads in
one process. Only the processed state goes to the cloud. The public dashboard
is live only while the laptop is publishing; otherwise it shows the last
snapshot and **Fog offline**.

---

## 1. Supabase: create the cloud database (≈10 min)

1. Sign up at <https://supabase.com> with GitHub or email. No card is needed.
2. **New project.** Pick any name, set a database password you will save, and
   choose the region nearest to you (for India, **Mumbai / ap-south-1**). Wait
   until the project is ready.
3. **SQL Editor → New query.** Paste all of [`supabase/schema.sql`](../supabase/schema.sql)
   and click **Run**. You should see "Success. No rows returned".
4. Copy three values. Supabase moves these pages around: look under
   **Project Settings → Data API / API Keys**, or click **Connect** at the top of
   the project.
   - the **Project URL** (`https://<ref>.supabase.co`)
   - the **Publishable key** (`sb_publishable_…`, or the legacy **anon** key)
   - the **Secret key** (`sb_secret_…`, or the legacy **service_role** key)

> The secret key can write anything in your project. Keep it in `.env` only:
> never commit it, put it in the dashboard, or paste it into Postman.

## 2. Configure the laptop (fog layer)

In the repo root, copy `.env.example` to `.env` and fill in:

```
ADMIN_API_KEY=<any long random string>
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
CLOUD_PUBLISH_INTERVAL=3
```

Generate an admin key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

## 3. Start the fog layer and check it publishes

```bash
pip install -r web/requirements.txt
python web/launch.py
```

The banner should say **Cloud sync: ON**. Then open <http://localhost:8000/health>:
`"cloud"` should show `"published"` increasing and `"last_error": null`.

In Supabase, **Table Editor → snapshots** should show one row, `live`, whose
`published_at` changes every few seconds.

| Symptom in `/health` → `last_error` | Fix |
|---|---|
| `HTTP 401` / `Invalid API key` | Wrong `SUPABASE_SECRET_KEY` |
| `HTTP 404` / relation does not exist | Run `supabase/schema.sql` |
| `HTTP 403` / permission denied | Re-run `supabase/schema.sql` (grants) |
| `URLError` / timed out | No internet, or wrong `SUPABASE_URL` |

## 4. Firebase: publish the dashboard (≈15 min)

1. Go to <https://console.firebase.google.com> → **Create a project**. You can
   turn Google Analytics off. The project stays on the free **Spark** plan;
   don't upgrade to Blaze. Note the **Project ID**.
2. Install Node.js LTS from <https://nodejs.org> if `node -v` doesn't work.
3. Build the cloud version of the dashboard. It reads `SUPABASE_URL` and
   `SUPABASE_PUBLISHABLE_KEY` from `.env`, and refuses to run if given a secret key.

```bash
python hosting/build.py
```

4. Log in to Firebase (opens a browser):

```bash
npx firebase-tools login
```

5. Deploy:

```bash
npx firebase-tools deploy --only hosting --project <your-project-id>
```

It prints **Hosting URL: `https://<your-project-id>.web.app`**. That is your
public dashboard.

To publish dashboard changes later, re-run steps 3 and 5.

## 5. Postman

1. Import `postman/WasteMgmt.postman_collection.json` and
   `postman/WasteMgmt.postman_environment.json`.
2. In the **Fog Waste Management** environment set:
   - `base_url` = `http://localhost:8000`
   - `admin_key` = your `ADMIN_API_KEY`
   - `supabase_url` = your Supabase project URL
   - `supabase_publishable_key` = the **publishable** key (never the secret one)
3. With the fog layer running, run the collection. There are 21 requests;
   folder **4. Cloud (Supabase)** proves that:
   - the dashboard can read the live snapshot
   - the public key **cannot** write (Row Level Security returns 401/403)
   - requests without a key are rejected

## 6. Demo day

1. Start the fog layer: `python web/launch.py`.
2. Open `https://<your-project-id>.web.app` on another device, such as your
   phone. It shows **Live** within a few seconds.
3. Show <http://localhost:8000> as the fog-side admin view: Start/Stop/Election
   work there, and the cloud dashboard follows a few seconds later.
4. Talking point: the footer of the cloud dashboard shows the fog → cloud sync
   time (`last sync … ms`), while routing decisions are made locally on the fog
   layer without waiting for the cloud.

## Evidence checklist

- Supabase: Table Editor showing the `live` row, and the RLS policy
  (Authentication → Policies)
- Firebase: Hosting dashboard showing the release and URL
- The public dashboard live on a phone
- Local `/health` showing `"cloud": {"enabled": true, ...}`
- Postman runner results, including the denied write
- A backup demo video

## Free-tier limits worth knowing

- **Supabase** pauses free projects after **7 days with no activity**. Restore
  the project from the Supabase dashboard (no data is lost). Open it a day or
  two before the demo.
- **Firebase Spark** hosting includes about 10 GB of transfer a month. The
  dashboard is about 60 KB per visit, so that is not a concern.
- **Supabase outbound data:** each open cloud dashboard reads about 25 KB every
  3 s (about 30 MB an hour). The free plan's monthly allowance covers many
  hours of viewing; close idle tabs anyway.
