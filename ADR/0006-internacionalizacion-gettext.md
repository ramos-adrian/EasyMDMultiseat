# ADR 0006 — Internacionalización con gettext, inglés como idioma fuente

- Estado: aceptado

## Contexto
La interfaz estaba escrita solo en español dentro del código. Se pidió soporte en/es sin dependencias nuevas, y el sistema no trae `xgettext`/`msgfmt`.

## Decisión
- `i18n.py` envuelve `gettext` (dominio `multiseat-manager`, catálogos en `locale/<lang>/LC_MESSAGES/`); `_()` se importa desde ahí. Idioma por entorno o `--lang`.
- Los msgids son inglés con placeholders con nombre (`{seat}`) para que el orden pueda variar por idioma; nada de f-strings dentro de `_()`.
- `tools/i18n.py` (Python puro) extrae con `ast`, sincroniza `.po`, valida placeholders y compila `.mo`. Los `.mo` se versionan para ejecutar desde el código fuente sin paso de build.
- Añadir un idioma = copiar el `.pot` a `locale/<lang>.po`, traducir y ejecutar `tools/i18n.py all`.

## Consecuencias
+ Sin dependencias. + Idiomas nuevos sin tocar código. − Hay que regenerar `.mo` tras cambiar textos; la traducción de nombres de categoría ocurre al construir la lista (cambiar de idioma requiere reiniciar).
