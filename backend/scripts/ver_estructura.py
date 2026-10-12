import os

def generate_structure_file(startpath, output_file='ESTRUCTURA_PROYECTO.txt'):
    # Carpetas a ignorar (RUIDO que no aporta al contexto del backend)
    ignored_dirs = {
        '.git', '__pycache__', 'venv', 'env', 'node_modules', 
        '.idea', '.vscode', 'BackupBD', 'backups', 'mongo_data'
    }
    
    # Extensiones a ignorar (Archivos binarios o irrelevantes para leer código)
    ignored_extensions = {
        '.pyc', '.png', '.jpg', '.jpeg', '.gif', '.ico', 
        '.zip', '.gz', '.pdf', '.exe', '.dll'
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"--- ESTRUCTURA DEL PROYECTO: {os.path.basename(os.path.abspath(startpath))} ---\n")
        f.write("(Generado automáticamente para contexto de IA)\n\n")

        for root, dirs, files in os.walk(startpath):
            # 1. Filtrar carpetas ignoradas in-place
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            
            # Cálculo de indentación
            level = root.replace(startpath, '').count(os.sep)
            indent = '│   ' * (level)
            
            # Escribir nombre de la carpeta actual
            folder_name = os.path.basename(root)
            if level == 0:
                f.write(f"{folder_name}/\n")
            else:
                f.write(f"{indent}├── {folder_name}/\n")
            
            subindent = '│   ' * (level + 1)
            
            # 2. Filtrar y escribir archivos
            for filename in sorted(files): # Ordenados alfabéticamente
                # Ignorar extensiones basura
                if any(filename.endswith(ext) for ext in ignored_extensions):
                    continue
                
                f.write(f"{subindent}├── {filename}\n")

    print(f"✅ ÉXITO: Estructura guardada en '{output_file}'")

if __name__ == '__main__':
    # Ejecutar en el directorio actual
    generate_structure_file('.')