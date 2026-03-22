# 🏗️ Imhotep Host

**A lightweight, self-hosted deployment engine using zero-trust network tunnels.**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-FastAPI-2b5b84.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ed.svg)

## The Problem: The "Heroku Void"
Hosting simple backend APIs, databases, or hobby projects has become prohibitively expensive. Existing self-hosted PaaS solutions (like Dokku or Coolify) are fantastic, but they require a public VPS, complex reverse-proxy configurations, and router port-forwarding. 

## The Solution: Native Sidecar Tunnels
**Imhotep Host** allows you to turn any local machine (like an old Mac mini or a Raspberry Pi or your old laptop) into a powerful PaaS without opening a single port on your router. 

Instead of a centralized proxy, Imhotep Host dynamically attaches a Zero-Trust network "sidecar" (Cloudflare/Tailscale) directly to each deployed app's isolated virtual network. Your apps securely punch a hole straight to the internet, bypassing your local firewall entirely.

### ✨ Features
- **UI-Driven:** No sysadmin skills required. Manage deployments via a clean React dashboard.
- **Zero-Trust Networking:** Automatic, secure public URLs via Cloudflare Quick Tunnels.
- **Automated Builds:** Paste a GitHub link, and the Python engine handles the Docker orchestration.
- **Custom Dockerfiles:** Use official community templates (Django, .NET, Node), or inject your own custom build scripts via the UI.
- **Local Databases:** Spin up isolated PostgreSQL instances that natively talk to your apps on a secure, internal Docker bridge network.

## 🚀 Getting Started (Coming Soon)
*Documentation and 1-click `docker-compose` installation instructions are currently under active development.*