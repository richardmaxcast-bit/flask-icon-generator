import requests
from PIL import Image, ImageEnhance
import os
import sys
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename # NOVIDADE: Importação para lidar com nomes de arquivo seguros

# --- CONFIGURAÇÃO DO FLASK ---
app = Flask(__name__)

# Define o diretório onde os ícones finais serão salvos
ICON_FOLDER = os.path.join(os.getcwd(), 'icons')
app.config['ICON_FOLDER'] = ICON_FOLDER

# Cria o diretório de ícones se não existir
if not os.path.exists(ICON_FOLDER):
    os.makedirs(ICON_FOLDER)

# Define as dimensões dos ícones a serem gerados
SIZES = [512, 192, 167, 152] 

# NOVIDADE: Extensões de arquivo permitidas para upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- FUNÇÕES DE PROCESSAMENTO DE IMAGEM (MANTIDAS) ---

def fetch_image_url_from_api(numberID):
    """Busca o URL do ícone na API."""
    api_url = f"https://social.maxcast.com.br/api/mobile-app/{numberID}"
    response = requests.get(api_url)
    response.raise_for_status() # Garante que erros 4xx/5xx sejam tratados como exceção
    data = response.json()
    
    if 'data' in data and 'images' in data['data'] and 'icon' in data['data']['images']:
        return data['data']['images']['icon']
    else:
        raise Exception(f"Imagem não encontrada para o ID: {numberID}.")

def download_image(url, save_to):
    """Baixa a imagem do URL para um caminho local."""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    if response.status_code == 200:
        with open(save_to, 'wb') as out_file:
            out_file.write(response.content)
    else:
        raise Exception(f"Erro ao baixar a imagem do URL: {url} (Status: {response.status_code})")

def preprocess_image(image_path):
    """Aplica o aumento de contraste à imagem."""
    try:
        with Image.open(image_path) as image:
            if image.mode != 'RGB':
                image = image.convert('RGB') # Garante o modo RGB para processamento
            
            enhancer = ImageEnhance.Contrast(image)
            enhanced_image = enhancer.enhance(1.5) 
            return enhanced_image
    except Exception as e:
        raise Exception(f"Erro ao pré-processar a imagem: {e}")

def resize_image(source_for_resizing, output_image_path, size):
    """Redimensiona uma imagem para o tamanho especificado."""
    with Image.open(source_for_resizing) as image:
        resized_image = image.resize((size, size), Image.Resampling.LANCZOS)
        resized_image.save(output_image_path)

def create_resized_images(source_image_path, sizes, output_dir, effective_id):
    """
    Controla o fluxo de pré-processamento, salvamento do base 512x512
    e criação dos tamanhos menores.
    """
    if not os.path.exists(source_image_path):
        raise Exception("O arquivo de origem temporário não existe.")
    
    # 1. Aplicar pré-processamento
    preprocessed_img = preprocess_image(source_image_path)
    
    # Define o nome de arquivo base (ex: icon-123-512x512.png)
    base_filename = f'icon-{effective_id}-512x512.png'
    original_image_output_path = os.path.join(output_dir, base_filename)
    
    # 2. Salvar a imagem base de 512x512 (após o pré-processamento)
    preprocessed_img.save(original_image_output_path) 

    # 3. Criar imagens redimensionadas a partir do arquivo salvo
    generated_files = [base_filename] 
    source_for_resizing = original_image_output_path
    
    for size in sizes:
        if size == 512:
            continue
            
        resized_filename = f'icon-{effective_id}-{size}x{size}.png'
        resized_image_output_path = os.path.join(output_dir, resized_filename)
        
        # Faz o resize do arquivo já processado e salvo
        resize_image(source_for_resizing, resized_image_output_path, size)
        generated_files.append(resized_filename)
        
    # Limpa o arquivo temporário inicial apenas se não for o arquivo final salvo
    if source_image_path != original_image_output_path and os.path.exists(source_image_path):
        os.remove(source_image_path)
        
    return generated_files

# --- ROTAS FLASK ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """Rota para exibir o formulário e processar a submissão."""
    temp_dir = os.path.join(os.getcwd(), 'temp')
    # Variável para rastrear o arquivo temporário
    source_image_path = None
    effective_id = None # ID que será usado para nomear os arquivos finais

    if request.method == 'POST':
        numberID = request.form.get('numberID', '').strip()
        file = request.files.get('image_file')

        # Cria a pasta temporária se não existir
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        # --- LÓGICA DE DECISÃO DA FONTE ---
        
        try:
            # 1. Tenta Upload de Arquivo
            if file and file.filename and allowed_file(file.filename):
                # Usa o nome do arquivo (sem extensão) como ID efetivo
                filename = secure_filename(file.filename)
                effective_id = filename.rsplit('.', 1)[0]
                
                # Salva o arquivo temporariamente no servidor
                source_image_path = os.path.join(temp_dir, filename)
                file.save(source_image_path)
                
            # 2. Tenta ID da API
            elif numberID and numberID.isdigit():
                effective_id = numberID
                
                # Lógica para obter URL e baixar
                image_url = fetch_image_url_from_api(numberID)
                source_image_path = os.path.join(temp_dir, f'temp_{numberID}.png')
                download_image(image_url, source_image_path)
                
            # 3. Nenhuma opção válida
            else:
                return render_template('index.html', error="Por favor, forneça um Número ID ou faça o upload de uma imagem válida.")

            # --- PROCESSAMENTO COMUM APÓS DEFINIR A FONTE ---
            
            if source_image_path and os.path.exists(source_image_path):
                # 4. Processar e criar os redimensionamentos
                generated_files = create_resized_images(source_image_path, SIZES, app.config['ICON_FOLDER'], effective_id)
                
                # Redireciona para a página de resultados
                return redirect(url_for('result', files=','.join(generated_files), numberID=effective_id))
            else:
                return render_template('index.html', error="Falha ao obter ou salvar a imagem de origem.")

        except requests.exceptions.HTTPError as e:
            # Captura erros de requisição HTTP (API ou Download)
            error_message = f"Erro HTTP: {e.response.status_code}. Imagem não encontrada para este ID."
            return render_template('index.html', error=error_message)
            
        except Exception as e:
            # Captura erros gerais (API, permissão, processamento)
            return render_template('index.html', error=f"Erro no processamento: {str(e)}")

        finally:
            # O arquivo temporário será limpo dentro de create_resized_images()
            # ou aqui se houver uma falha antes
            if 'source_image_path' in locals() and source_image_path and os.path.exists(source_image_path):
                try:
                    os.remove(source_image_path)
                except Exception:
                    # Ignora falhas de limpeza, o sistema tentará na próxima vez.
                    pass

    return render_template('index.html', error=None)

@app.route('/result')
def result():
    """Rota para exibir os links de download dos ícones gerados."""
    files_str = request.args.get('files')
    numberID = request.args.get('numberID')
    
    if not files_str:
        return redirect(url_for('index'))
        
    generated_files = files_str.split(',')
    
    files_data = [{'name': f, 'url': url_for('download_file', filename=f)} for f in generated_files]

    return render_template('result.html', files_data=files_data, numberID=numberID)

@app.route('/download/<filename>')
def download_file(filename):
    """Rota para servir os arquivos para download."""
    return send_from_directory(app.config['ICON_FOLDER'], filename, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)

# CODIGÃO COM GOK, COMENTARIO FEITO POR ELE MESMO ABRAÇOS RICHARD MAX