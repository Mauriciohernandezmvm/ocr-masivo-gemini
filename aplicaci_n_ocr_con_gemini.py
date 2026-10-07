import streamlit as st
import google.generativeai as genai
import os
import tempfile
import zipfile
import io
import pandas as pd
import time

# --- Configuración de página ---
st.set_page_config(page_title="Lector OCR Masivo", page_icon="📄", layout="wide")

# --- Sistema de Autenticación Básica ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Ingresa la contraseña:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Ingresa la contraseña:", type="password", on_change=password_entered, key="password")
        st.error("Contraseña incorrecta.")
        return False
    return True

if not check_password():
    st.stop()

# --- Configuración de Gemini ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("⚠️ Falta configurar la variable GEMINI_API_KEY en los Secrets de Streamlit.")
    st.stop()

# Usamos gemini-1.5-flash, ideal para tareas masivas y multimodales (PDFs, imágenes)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- Interfaz Principal ---
st.title("📄 Lector OCR Masivo de Hojas de Ruta")
st.markdown("Sube tus documentos para extraer la información. **Formatos soportados: PDF, PNG, JPG, JPEG.**")

# ACEPTA MULTIPLES FORMATOS
archivos_subidos = st.file_uploader(
    "Selecciona o arrastra los archivos", 
    type=["pdf", "png", "jpg", "jpeg"], 
    accept_multiple_files=True
)

if archivos_subidos:
    if st.button("🚀 Iniciar Procesamiento Masivo"):
        resultados = []
        
        # Componentes visuales de progreso
        barra_progreso = st.progress(0)
        texto_estado = st.empty()
        
        total_archivos = len(archivos_subidos)
        
        for i, archivo in enumerate(archivos_subidos):
            texto_estado.markdown(f"**Procesando ({i+1}/{total_archivos}):** `{archivo.name}`...")
            
            try:
                # 1. Extraer la extensión para crear el archivo temporal adecuado
                extension = archivo.name.split('.')[-1].lower()
                
                # 2. Guardar temporalmente en el servidor para que Gemini pueda leerlo
                with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extension}") as tmp_file:
                    tmp_file.write(archivo.getvalue())
                    tmp_ruta = tmp_file.name
                
                # 3. Subir el archivo a la API de Gemini (File API)
                archivo_gemini = genai.upload_file(tmp_ruta)
                
                # 4. Esperar a que el archivo esté listo (importante para PDFs pesados)
                while archivo_gemini.state.name == "PROCESSING":
                    time.sleep(2)
                    archivo_gemini = genai.get_file(archivo_gemini.name)
                    
                if archivo_gemini.state.name == "FAILED":
                    raise Exception("El procesamiento del archivo falló en los servidores de Google.")
                
                # 5. Generar la extracción de texto
                prompt = "Extrae todo el texto de este documento/hoja de ruta de forma precisa. Mantén los datos organizados, respetando tablas y la estructura original lo mejor posible. No añadas introducciones ni saludos, solo el texto extraído."
                response = model.generate_content([archivo_gemini, prompt])
                
                # 6. Limpiar: Borrar de Gemini y del servidor local
                genai.delete_file(archivo_gemini.name)
                os.remove(tmp_ruta)
                
                # 7. Guardar resultado
                resultados.append({
                    "Nombre de Archivo": archivo.name,
                    "Texto Extraído": response.text,
                    "Estado": "Éxito ✅"
                })
                
            except Exception as e:
                # Si un archivo falla, lo registramos pero el bucle continúa con los demás
                resultados.append({
                    "Nombre de Archivo": archivo.name,
                    "Texto Extraído": f"Error: {str(e)}",
                    "Estado": "Error ❌"
                })
            
            # Actualizar progreso y hacer una breve pausa para respetar límites de la API
            barra_progreso.progress((i + 1) / total_archivos)
            time.sleep(2) 
            
        texto_estado.success(f"✅ ¡Procesamiento completado! Se procesaron {total_archivos} archivos.")
        
        # --- Generar Descargables ---
        
        # 1. Crear ZIP con todos los textos (.txt)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for res in resultados:
                # Cambiar la extensión original a .txt
                nombre_base = os.path.splitext(res['Nombre de Archivo'])[0]
                nombre_txt = f"{nombre_base}.txt"
                zip_file.writestr(nombre_txt, res['Texto Extraído'])
                
        # 2. Crear CSV resumen
        df = pd.DataFrame(resultados)
        # utf-8-sig para que Excel lea las tildes bien
        csv_data = df.to_csv(index=False).encode('utf-8-sig')
        
        # Mostrar botones
        st.markdown("### 📥 Descarga tus resultados")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📦 Descargar Textos (Archivo ZIP)",
                data=zip_buffer.getvalue(),
                file_name="hojas_de_ruta_procesadas.zip",
                mime="application/zip",
                use_container_width=True
            )
        with col2:
            st.download_button(
                label="📊 Descargar Reporte Resumen (CSV)",
                data=csv_data,
                file_name="reporte_estado.csv",
                mime="text/csv",
                use_container_width=True
            )
