import os
import subprocess
import tempfile
import time
import re # Importiere das 're'-Modul für reguläre Ausdrücke
import shutil # Importiere shutil für rmtree
from flask import Flask, render_template, request, send_file, after_this_request, jsonify # Importiere jsonify

app = Flask(__name__)

# Konfiguration für den Download-Ordner
# Verwende einen 'temp'-Ordner im selben Verzeichnis wie die app.py
# Erstellen Sie einen temporären Ordner, um Downloads zu speichern.
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "temp", "youtube_downloads")

# Funktion zum Bereinigen des Download-Verzeichnisses beim Start der App
def cleanup_download_directory():
    if os.path.exists(DOWNLOAD_DIR):
        print(f"Reinige vorhandenen Download-Ordner: {DOWNLOAD_DIR}")
        try:
            shutil.rmtree(DOWNLOAD_DIR)
            print(f"Ordner {DOWNLOAD_DIR} erfolgreich bereinigt.")
        except OSError as e:
            print(f"Fehler beim Reinigen des Ordners {DOWNLOAD_DIR}: {e}")
            return False # Indicate failure
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"Download-Ordner bereit: {DOWNLOAD_DIR}")
    return True # Indicate success

# cleanup_download_directory() wird vor dem ersten Request aufgerufen, wenn die App startet.
# Dies ist eine einfache Methode für die Entwicklungsumgebung.
# Für Produktion würde man einen anderen Ansatz für die Bereinigung wählen.
with app.app_context():
    cleanup_download_directory()

def parse_time_to_seconds(time_str):
    """
    Konvertiert einen Zeitstring im Format MM:SS in Sekunden.
    Gibt None zurück, wenn der String leer ist, und löst ValueError bei ungültigem Format aus.
    """
    if not time_str:
        return None
    
    parts = time_str.split(':')
    if len(parts) == 2:
        try:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        except ValueError:
            raise ValueError("Ungültiges Zeitformat. Bitte verwenden Sie MM:SS.")
    else:
        raise ValueError("Ungültiges Zeitformat. Bitte verwenden Sie MM:SS.")


@app.route('/', methods=['GET'])
def index():
    """Rendert die Hauptseite der Anwendung."""
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    """
    Verarbeitet die Download-Anfrage vom Benutzer.
    Lädt ein YouTube-Video als MP3 oder MP4 herunter und schneidet es bei Bedarf zu.
    """
    video_url = request.form.get('video_url')
    file_format = request.form.get('format')
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')

    if not video_url:
        return render_template('index.html', message="Bitte geben Sie eine Video-URL ein.", is_error=True)

    start_time_seconds = None
    end_time_seconds = None
    try:
        start_time_seconds = parse_time_to_seconds(start_time_str)
        end_time_seconds = parse_time_to_seconds(end_time_str)
    except ValueError as e:
        return render_template('index.html', message=str(e), is_error=True)

    # Verwende yt-dlp, um die Video-ID und den Titel für vorhersagbare Dateinamen zu erhalten
    # Verbessert: Verwende --print für robustere Ausgabe
    info_command = ['yt-dlp', '--print', '%(id)s\n%(title)s', video_url]
    try:
        info_process = subprocess.run(info_command, capture_output=True, text=True, check=True)
        # Überprüfe, ob die Ausgabe zwei Zeilen enthält
        info_lines = info_process.stdout.strip().split('\n')
        if len(info_lines) < 2:
            raise ValueError(f"Unerwartete Ausgabe von yt-dlp info command: {info_process.stdout}")
        video_id = info_lines[0]
        video_title = info_lines[1]
        
        # Titel für den Dateinamen bereinigen, um ungültige Zeichen zu entfernen
        sanitized_title = re.sub(r'[\\/:*?"<>|]', '', video_title)
        print(f"Debug: Original Video Titel: '{video_title}'")
        print(f"Debug: Bereinigter Titel (sanitized_title): '{sanitized_title}'")
    except subprocess.CalledProcessError as e:
        return render_template('index.html', message=f"Fehler beim Abrufen der Videoinformationen: {e.stderr}", is_error=True)
    except Exception as e:
        return render_template('index.html', message=f"Ein unerwarteter Fehler ist beim Abrufen der Videoinformationen aufgetreten: {e}", is_error=True)


    # Definiere temporären vollständigen Download-Pfad basierend auf dem bereinigten Titel und Format
    temp_full_file_ext = 'mp4' if file_format == 'mp4' else 'mp3'
    # Verwende den bereinigten Titel und eine eindeutige ID (Zeitstempel) für den temporären Dateinamen
    # um Konflikte bei mehreren Downloads zu vermeiden
    unique_suffix = int(time.time() * 1000) # Millisekunden-Timestamp
    temp_full_file_name = f"{sanitized_title}_{unique_suffix}_full.{temp_full_file_ext}"
    temp_full_file_path = os.path.join(DOWNLOAD_DIR, temp_full_file_name)

    # yt-dlp Befehl, um das vollständige Video/Audio herunterzuladen
    yt_dlp_command = ['yt-dlp']
    if file_format == 'mp3':
        yt_dlp_command.extend(['-x', '--audio-format', 'mp3', '-o', temp_full_file_path])
    elif file_format == 'mp4':
        yt_dlp_command.extend(['-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]', '-o', temp_full_file_path])
    yt_dlp_command.append(video_url)

    try:
        # Führe den yt-dlp Befehl aus, um die vollständige Datei herunterzuladen
        print(f"Downloading full file with command: {' '.join(yt_dlp_command)}")
        subprocess.run(yt_dlp_command, capture_output=True, text=True, check=True)
        print(f"Full file downloaded to: {temp_full_file_path}")
        
        # Gib dem Dateisystem einen kleinen Moment zum Synchronisieren
        time.sleep(1)

        # Prüfe, ob die vollständige Datei tatsächlich existiert
        if not os.path.exists(temp_full_file_path):
            return render_template('index.html', message=f"Fehler: Volle Datei wurde nicht heruntergeladen. Pfad: {temp_full_file_path}", is_error=True)

    except subprocess.CalledProcessError as e:
        error_message = f"Download der vollständigen Datei fehlgeschlagen. Fehlercode: {e.returncode}\nstdout: {e.stdout}\nstderr: {e.stderr}"
        print(error_message)
        return render_template('index.html', message=error_message, is_error=True)
    except Exception as e:
        error_message = f"Ein unerwarteter Fehler ist beim Download der vollständigen Datei aufgetreten: {e}"
        print(error_message)
        return render_template('index.html', message=error_message, is_error=True)

    final_file_path = temp_full_file_path
    
    # Wenn Zuschneiden angefordert wird, führe ffmpeg aus, um die Datei zuzuschneiden
    if start_time_seconds is not None or end_time_seconds is not None:
        # Dateiname für die zugeschnittene Datei: Originaltitel-Trimmed.ext
        trimmed_file_name = f"{sanitized_title}-Trimmed.{temp_full_file_ext}"
        trimmed_file_path = os.path.join(DOWNLOAD_DIR, trimmed_file_name)
        
        ffmpeg_trim_command = ['ffmpeg', '-i', temp_full_file_path]

        if start_time_seconds is not None:
            ffmpeg_trim_command.extend(['-ss', str(start_time_seconds)])
        
        # ffmpegs -to ist absolut, -t ist Dauer
        if end_time_seconds is not None:
            if start_time_seconds is not None:
                duration_seconds = end_time_seconds - start_time_seconds
                if duration_seconds <= 0:
                    # Clean up the initial full file immediately if times are invalid
                    os.remove(temp_full_file_path)
                    return render_template('index.html', message="Endzeit muss nach der Startzeit liegen.", is_error=True)
                ffmpeg_trim_command.extend(['-t', str(duration_seconds)])
            else:
                ffmpeg_trim_command.extend(['-to', str(end_time_seconds)])

        # Sicherstellen, dass die Ausgabe für präzises Zuschneiden neu kodiert wird, besonders für Videos.
        # Für Audio ist es oft eine Kopie, aber für Video ist eine erneute Kodierung für Schnitte sicherer.
        if file_format == 'mp4':
            # Verwende 'libx264' und 'aac' für eine robuste Neukodierung.
            ffmpeg_trim_command.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23'])
            ffmpeg_trim_command.extend(['-c:a', 'aac', '-b:a', '128k'])
        elif file_format == 'mp3':
            # Für MP3 einfach sicherstellen, dass die Ausgabe MP3 ist
            ffmpeg_trim_command.extend(['-c:a', 'libmp3lame', '-b:a', '128k'])

        ffmpeg_trim_command.append(trimmed_file_path)

        try:
            print(f"Trimming file with command: {' '.join(ffmpeg_trim_command)}")
            subprocess.run(ffmpeg_trim_command, capture_output=True, text=True, check=True)
            print(f"File trimmed to: {trimmed_file_path}")
            
            # Gib dem Dateisystem einen kleinen Moment zum Synchronisieren
            time.sleep(1)

            if not os.path.exists(trimmed_file_path):
                # Clean up the initial full file immediately if trimming failed
                os.remove(temp_full_file_path)
                return render_template('index.html', message=f"Fehler: Die zugeschnittene Datei wurde nicht erstellt. Pfad: {trimmed_file_path}", is_error=True)
            
            final_file_path = trimmed_file_path
            # Ursprüngliche vollständige Datei nach erfolgreichem Zuschneiden bereinigen
            try:
                os.remove(temp_full_file_path)
                print(f"Original full file deleted: {temp_full_file_path}")
            except Exception as e:
                print(f"Fehler beim Löschen der Originaldatei {temp_full_file_path}: {e}")

        except subprocess.CalledProcessError as e:
            # Clean up the initial full file if trimming failed
            os.remove(temp_full_file_path)
            error_message = f"Zuschneiden fehlgeschlagen. Fehlercode: {e.returncode}\nstdout: {e.stdout}\nstderr: {e.stderr}"
            print(error_message)
            return render_template('index.html', message=error_message, is_error=True)
        except Exception as e:
            # Clean up the initial full file if trimming failed
            os.remove(temp_full_file_path)
            error_message = f"Ein unerwarteter Fehler ist beim Zuschneiden aufgetreten: {e}"
            print(error_message)
            return render_template('index.html', message=error_message, is_error=True)

    # Definiere den Dateinamen, der dem Benutzer präsentiert werden soll
    # Wenn Start- oder Endzeit angegeben wurden, füge "-Trimmed" hinzu
    filename_for_user = f"{sanitized_title}.{temp_full_file_ext}"
    if start_time_seconds is not None or end_time_seconds is not None:
        filename_for_user = f"{sanitized_title}-Trimmed.{temp_full_file_ext}"

    print(f"Debug: Finaler Dateipfad für Download: {final_file_path}")
    print(f"Debug: Dateiname für den Benutzer (download_name): {filename_for_user}")

    @after_this_request
    def remove_file(response):
        """Löscht die endgültige Datei nach dem Senden."""
        print(f"Versuche Datei zu löschen: {final_file_path}")
        if os.path.exists(final_file_path):
            try:
                os.remove(final_file_path)
                print(f"Endgültige Datei '{final_file_path}' gelöscht.")
            except Exception as e:
                print(f"Fehler beim Löschen der endgültigen Datei '{final_file_path}': {e}")
        else:
            print(f"Datei '{final_file_path}' nicht gefunden zum Löschen (möglicherweise bereits gelöscht oder nie existiert).")
        
        # Optional: Versuche, das 'youtube_downloads'-Verzeichnis zu löschen, wenn es leer ist.
        # Dies kann problematisch sein, wenn mehrere Downloads gleichzeitig laufen,
        # aber für eine Einzelnutzer-App im Entwicklungsmodus ist es ok.
        parent_dir = os.path.dirname(final_file_path)
        if os.path.exists(parent_dir) and not os.listdir(parent_dir):
            try:
                os.rmdir(parent_dir)
                print(f"Leeres Verzeichnis '{parent_dir}' gelöscht.")
            except OSError as e:
                print(f"Fehler beim Löschen des leeren Verzeichnisses '{parent_dir}': {e}")

        return response

    return send_file(final_file_path, as_attachment=True, download_name=filename_for_user)

@app.route('/clear_cache', methods=['POST'])
def clear_cache():
    """Löscht den gesamten Inhalt des Download-Verzeichnisses."""
    print("Anfrage zum Löschen des Caches erhalten.")
    if cleanup_download_directory():
        return jsonify({"status": "success", "message": "Cache erfolgreich gelöscht."}), 200
    else:
        return jsonify({"status": "error", "message": "Fehler beim Löschen des Caches."}), 500


if __name__ == '__main__':
    app.run(debug=True)
