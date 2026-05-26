# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Django 5.2.6 inventory management web application (in Spanish) for warehouse counting workflows. Uses Oracle Database via direct SQL queries (not Django ORM), with external ASEYCO authentication service.

## Commands

```bash
# Development server
python manage.py runserver

# Production server (Waitress on port 3004, 4 threads)
python run_production.py

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Collect static files for production
set DJANGO_SETTINGS_MODULE=core.settings_prod
python manage.py collectstatic --noinput

# Run tests
python manage.py test

# Deployment check
python manage.py check --deploy
```

## Architecture

### Settings Split
- `core/settings.py` — development settings, environment-based Oracle configuration, auth backends
- `core/settings_prod.py` — extends dev settings: `DEBUG=False`, Whitenoise middleware, logging to `logs/django_error.log`

### Database
All database access uses **raw Oracle SQL** via `connection.cursor()` — Django ORM is not used. `inventario/models.py` is intentionally empty. Configure Oracle connection values with `ORACLE_DB_NAME`, `ORACLE_DB_USER`, and `ORACLE_DB_PASSWORD`.

### Authentication
Custom backend in `core/settings.py` (`AUTHENTICATION_BACKENDS`). Login at `/` or `/login/` calls the external ASEYCO nomina web service. Session stores: `cedula`, `nombre`, `empresa`, `cargo`, `email`, `region`. Users must have `ESTADO='1'` in the external system.

### Main App: `inventario`
- `inventario/views.py` — ~6,400 lines with 50+ view functions covering all business logic
- `core/urls.py` — 67 URL routes
- `templates/inventario/` — 14 HTML templates
- `inventario/templatetags/custom_filters.py` — `format_number` and `format_currency` filters

### Business Domains
- **Conteos** (counting): nuevo_conteo → primer_conteo → segundo_conteo → gestion_conteos
- **Piqueos** (picking/sampling): administracion, asignacion de colaboradores, secuenciales
- **Actas Preliminares**: preliminary report generation (PDF via ReportLab, including barcodes)
- **Roles**: regular users, supervisors/jefes, Django admin

### Key Dependencies
| Package | Purpose |
|---------|---------|
| `oracledb` | Oracle DB driver |
| `waitress` | Production WSGI server (Windows) |
| `whitenoise` | Static file serving |
| `reportlab` | PDF and barcode generation |
| `requests` | External ASEYCO authentication calls |

## Deployment (Windows)

Production runs as a Windows service managed by NSSM. See `INSTALACION_PRODUCCION.md` for full setup. PowerShell scripts `install_production.ps1` and `install_service.ps1` automate the setup.
