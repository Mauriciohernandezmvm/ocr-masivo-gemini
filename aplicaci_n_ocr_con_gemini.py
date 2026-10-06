import streamlit as st
import google.generativeai as genai
import tempfile
import os
import time
import pandas as pd
import zipfile
import io

st.set_page_config(page_title="Extractor OCR Masivo", page_icon="📄", layout="centered")

def check_password():
    """Valida la contraseña para proteger el acceso a la aplicación."""
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Eliminar por seguridad
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "🔒 Ingresa la contraseña para acceder a la aplicación:", 
            type="password", 
            on_change=password_entered, 
            key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "🔒 Ingresa la contraseña para acceder a la aplicación:", 
            type="password", 
            on_change=password_entered, 
            key="password"
        )
        st.error("Contraseña incorrecta. Inténtalo de nuevo.")
        return False
    return True

if check_password():
    st.title("📄 Extractor de Texto OCR Masivo")
    st.markdown("Sube hasta 1000 documentos PDF. El sistema extraerá el texto de cada uno utilizando Inteligencia Artificial.")

    # Configuración de Gemini API (la llave se toma de los secretos de Streamlit)
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Usamos el modelo flash por su rapidez y menor costo, ideal para OCR masivo
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        st.error(f"Error al configurar la API: {e}")
        st.stop()

    uploaded_files = st.file_uploader("Selecciona los archivos PDF", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        st.info(f"Has cargado {len(uploaded_files)} archivo(s).")
        
        if st.button("🚀 Iniciar Extracción OCR", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results = []
            
            for index, uploaded_file in enumerate(uploaded_files):
                filename = uploaded_file.name
                status_text.text(f"Procesando ({index + 1}/{len(uploaded_files)}): {filename}...")
                
                # Crear un archivo temporal ya que la API File de Gemini requiere una ruta de archivo
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_path = tmp_file.name
                
                try:
                    gemini_file = genai.upload_file(tmp_path, mime_type="application/pdf")
                    
                    # Prompt específico para OCR
                    prompt = """
                    Actúa como un sistema OCR de alta precisión. 
                    Extrae todo el texto de este documento. 
                    Mantén la estructura, los párrafos y omite describir imágenes, solo devuelve el texto puro contenido en el documento.
                    """
                    
                    response = model.generate_content([gemini_file, prompt])
                    extracted_text = response.text
                    
                    results.append({
                        "Nombre del Archivo": filename,
                        "Texto Extraído": extracted_text,
                        "Estado": "Éxito"
                    })
                    
                    # Limpieza del archivo en la nube de Gemini para no saturar el almacenamiento
                    genai.delete_file(gemini_file.name)
                    
                except Exception as e:
                    results.append({
                        "Nombre del Archivo": filename,
                        "Texto Extraído": "",
                        "Estado": f"Error: {str(e)}"
                    })
                finally:
                    # Limpieza del archivo temporal local
                    os.remove(tmp_path)
                
                # Actualizar barra de progreso
                progress = (index + 1) / len(uploaded_files)
                progress_bar.progress(progress)
                
                # Pausa estratégica para evitar exceder los límites de la API (Rate limits)
                if index < len(uploaded_files) - 1:
                    time.sleep(2) 
            
            status_text.text("✅ ¡Procesamiento completado!")
            st.success("Se ha extraído el texto de todos los documentos.")
            
            # Convertir resultados a DataFrame para fácil manejo
            df_results = pd.DataFrame(results)
            
            st.subheader("Resultados")
            st.dataframe(df_results[["Nombre del Archivo", "Estado"]])
            
            # Crear archivo CSV
            csv = df_results.to_csv(index=False).encode('utf-8')
            
            # Crear archivo ZIP con archivos de texto individuales
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                for res in results:
                    # Crear un nombre de archivo .txt válido
                    txt_filename = res["Nombre del Archivo"].replace(".pdf", ".txt")
                    zip_file.writestr(txt_filename, res["Texto Extraído"])
            
            # Botones de descarga
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📥 Descargar CSV Consolidado",
                    data=csv,
                    file_name="resultados_ocr.csv",
                    mime="text/csv",
                )
            with col2:
                st.download_button(
                    label="🗂️ Descargar ZIP (Archivos TXT)",
                    data=zip_buffer.getvalue(),
                    file_name="textos_extraidos.zip",
                    mime="application/zip",
                )