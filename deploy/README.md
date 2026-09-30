# Deploying to Google Cloud (e2-micro, Always Free)

This runs the whole system on one VM: the bin simulator, all fog nodes (as threads in one
process), and the FastAPI dashboard/API. nginx is the public entry point on port 80 and
proxies to uvicorn on `127.0.0.1:8000`.

```
Browser / Postman ──HTTP:80──▶ nginx (gzip) ──▶ uvicorn :8000 (1 worker)
                                                  └─ FastAPI (web/app.py)
                                                       └─ BinSimulator + FogNodeSimulator (threads)
```

> **Scope:** the fog nodes are threads inside a single process on a single VM. This is a
> deployed *simulation* of a fog architecture, not a multi-machine deployment.

## What is free, and what is not

| Item | Cost |
|---|---|
| 1 × e2-micro VM in `us-central1`, `us-west1` or `us-east1` | Free (Always Free tier) |
| Up to 30 GB **Standard** persistent disk | Free. The default "Balanced" disk is **not** free |
| External IPv4 address | Charged (a few $/month). Covered by the $300 / 90-day trial credit |
| Egress above 1 GB/month | Charged (~$0.12/GB). The nginx gzip config keeps this small |

A free-trial account is **not billed** unless you click "Activate full account". A card is
still required at signup.

## 1. One-time GCP setup (console)

1. Sign up at <https://cloud.google.com/free> and start the free trial.
2. **Billing → Budgets & alerts → Create budget.** Set $1 with alerts at 50 / 90 / 100 %.
   Do this first.
3. Create a project and enable the **Compute Engine API**.

## 2. Create the VM

**Compute Engine → VM instances → Create instance.** Each of these settings matters for
staying inside the free tier:

| Setting | Value |
|---|---|
| Region | `us-central1` (or `us-west1` / `us-east1`) |
| Machine type | `e2-micro` |
| Boot disk | Ubuntu 24.04 LTS, **Standard persistent disk**, 20 GB |
| Firewall | Tick **Allow HTTP traffic** |
| Networking → Network service tier | **Standard** |
| External IPv4 | Ephemeral |

The ephemeral IP **changes if you stop and start the VM**. Reserving a static IP fixes
that, but a reserved IP is billed even while the VM is stopped.

## 3. Lock down SSH

**VPC network → Firewall → `default-allow-ssh` → Edit.** Change the source range from
`0.0.0.0/0` to your own IP (`<your-ip>/32`). If the browser **SSH** button then stops
working, also add `35.235.240.0/20` (Google's IAP range).

## 4. Deploy

Push this repository to GitHub first, because the script clones it. Then open **SSH** on
the VM and run:

```bash
curl -fsSL https://raw.githubusercontent.com/arnav-pawaskar/WasteManagmentSystem/main/deploy/setup.sh -o setup.sh
sudo bash setup.sh
```

On its first run the script asks for an admin key. Leave it blank to have one generated,
and **save the key it prints**. The key is stored only in `/etc/wms.env` (mode 600).

When it finishes, open:

- Dashboard: `http://<EXTERNAL_IP>/`
- API docs (Swagger): `http://<EXTERNAL_IP>/docs`

To deploy new code later, push to GitHub and re-run `sudo bash setup.sh`.

## 5. Operate

```bash
sudo systemctl status waste-mgmt      # is it running?
sudo journalctl -u waste-mgmt -f      # live logs
sudo systemctl restart waste-mgmt     # restart (the simulation resets)
sudoedit /etc/wms.env                 # change ADMIN_API_KEY, then restart
```

## 6. Test with Postman

1. Import `postman/WasteMgmt.postman_collection.json` and
   `postman/WasteMgmt.postman_environment.json`.
2. In the **Fog Waste Management** environment, set `base_url` to `http://<EXTERNAL_IP>`
   and `admin_key` to your key. Keep the key out of the committed file.
3. Run the collection with the **Collection Runner**, in order. The run contains 18
   requests covering public reads, auth and validation failures (401/422/400/404), and
   admin actions. It ends with the simulation running.

## 7. Evidence checklist

- The VM details page, showing e2-micro and the free region
- The firewall rules (HTTP open, SSH restricted)
- The budget alert
- `systemctl status waste-mgmt`
- `/docs` on the public IP
- Postman runner results, against localhost and against the VM
- The dashboard live on the public IP
- A 401 on an admin call made without the key

Record a backup video of the demo in case the network fails.

## Known limitations

- **HTTP only.** Without a domain there is no simple TLS, so the admin key travels in
  clear text. That is acceptable for a class demo; rotate the key afterwards.
- Single process on a single VM. The ledger and all simulation state are in memory and
  reset on restart.
- One shared simulation for all viewers. Only admin-key holders can start, stop or
  reconfigure it.

## After grading

**Delete** the VM (and any reserved static IP) under Compute Engine → VM instances.
