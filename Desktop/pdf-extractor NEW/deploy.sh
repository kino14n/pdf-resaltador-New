#!/bin/bash

PROYECTO_PATH="/c/Users/Usuario/Desktop/pdf-resaltador"

cd "$PROYECTO_PATH" || { echo "ERROR: No existe la carpeta $PROYECTO_PATH"; exit 1; }

echo "🚀 Deploy automático desde $PROYECTO_PATH a GitHub"

echo "🔄 Actualizando repositorio local..."
git pull origin master

echo "➕ Añadiendo todos los cambios..."
git add .

echo "📝 Escribí el mensaje del commit:"
read -r MENSAJE

if [ -z "$MENSAJE" ]; then
  MENSAJE="Actualización automática"
fi

echo "💾 Commit con mensaje: $MENSAJE"
git commit -m "$MENSAJE" || echo "Nada para commitear."

echo "⬆️ Enviando cambios a origin master..."
git push origin master

echo "✅ Deploy completado."