import requests
from PIL import Image, ImageEnhance
import os
import sys
from flask import Flask, render_template, request, redirect, url_for, send_from_directory

# --- CONFIGURAÇÃO DO FLASK ---
app = Flask(__name__)

# Define o diretório onde os ícones finais serão salvos
# Ele será criado na mesma pasta onde o app.py está (ex: /seu_projeto/icons)
ICON_FOLDER = os.path.join(os.getcwd(), 'icons')
app.config['ICON_FOLDER'] = ICON_FOLDER

# Cria o diretório de ícones se não existir
if not os.path.exists(ICON_FOLDER):
    os.makedirs(ICON_FOLDER)

# Define as dimensões dos ícones a serem gerados
# 512 é o tamanho base que será renomeado/salvo
SIZES = [512, 192, 167, 152] 

# --- FUNÇÕES DE PROCESSAMENTO DE IMAGEM ---

def fetch_image_url_from_api(numberID):
    """Busca o URL do ícone na API."""
    api_url = f"https://social.maxcast.com.br/api/mobile-app/{numberID}"
    response = requests.get(api_url)
    data = response.json()
    
    if 'data' in data and 'images' in data['data'] and 'icon' in data['data']['images']:
        return data['data']['images']['icon']
    else:
        # Erro customizado para o Flask capturar
        raise Exception(f"Imagem não encontrada para o ID: {numberID}.")

def download_image(url, save_to):
    """Baixa a imagem do URL para um caminho local."""
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(save_to, 'wb') as out_file:
            out_file.write(response.content)
    else:
        raise Exception(f"Erro ao baixar a imagem do URL: {url} (Status: {response.status_code})")

def preprocess_image(image_path):
    """Aplica o aumento de contraste à imagem."""
    with Image.open(image_path) as image:
        enhancer = ImageEnhance.Contrast(image)
        # Aumenta o contraste em 50%
        enhanced_image = enhancer.enhance(1.5) 
        return enhanced_image

def resize_image(source_image_path, output_image_path, size):
    """Redimensiona uma imagem para o tamanho especificado."""
    with Image.open(source_image_path) as image:
        # Usando LANCZOS para melhor qualidade de redimensionamento
        resized_image = image.resize((size, size), Image.Resampling.LANCZOS)
        resized_image.save(output_image_path)

def create_resized_images(source_image_path, sizes, output_dir, numberID):
    """
    Controla o fluxo de pré-processamento, salvamento do base 512x512
    e criação dos tamanhos menores.
    """
    if not os.path.exists(source_image_path):
        raise Exception("O arquivo de origem temporário não existe.")
    
    # 1. Aplicar pré-processamento e salvar de volta
    preprocessed_img = preprocess_image(source_image_path)
    preprocessed_img.save(source_image_path) 
    
    # Define o nome de arquivo base (ex: icon-123-512x512.png)
    base_filename = f'icon-{numberID}-512x512.png'
    original_image_output_path = os.path.join(output_dir, base_filename)
    
    # Renomeia o arquivo temporário para o nome final
    if os.path.exists(original_image_output_path):
        os.remove(original_image_output_path)
        
    os.rename(source_image_path, original_image_output_path)

    # 3. Criar imagens redimensionadas
    source_for_resizing = original_image_output_path
    generated_files = [base_filename] 
    
    for size in sizes:
        if size == 512:
            continue
            
        resized_filename = f'icon-{numberID}-{size}x{size}.png'
        resized_image_output_path = os.path.join(output_dir, resized_filename)
        
        resize_image(source_for_resizing, resized_image_output_path, size)
        generated_files.append(resized_filename)
        
    return generated_files

# --- ROTAS FLASK ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """Rota para exibir o formulário e processar a submissão do ID."""
    temp_dir = os.path.join(os.getcwd(), 'temp')
    
    if request.method == 'POST':
        numberID = request.form.get('numberID')
        
        if not numberID:
            return render_template('index.html', error="Por favor, digite um número ID.")

        # Lógica de processamento
        try:
            # 1. Obter URL
            image_url = fetch_image_url_from_api(numberID)
            
            # 2. Configurar pasta temporária e caminho
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            source_image_path = os.path.join(temp_dir, f'temp_{numberID}.png')
            
            # 3. Baixar imagem
            download_image(image_url, source_image_path)
            
            # 4. Processar e criar os redimensionamentos
            generated_files = create_resized_images(source_image_path, SIZES, app.config['ICON_FOLDER'], numberID)
            
            # Redireciona para a página de resultados
            return redirect(url_for('result', files=','.join(generated_files), numberID=numberID))
        
        except Exception as e:
            # Limpeza do arquivo temporário em caso de falha, se ele ainda existir
            if 'source_image_path' in locals() and os.path.exists(source_image_path):
                os.remove(source_image_path)
            return render_template('index.html', error=f"Erro ao processar: {str(e)}")

    # Limpeza de arquivos temporários antigos (opcional)
    # Recomendado: Adicionar uma função de limpeza agendada para limpar a pasta 'temp' periodicamente.

    return render_template('index.html', error=None)

@app.route('/result')
def result():
    """Rota para exibir os links de download dos ícones gerados."""
    files_str = request.args.get('files')
    numberID = request.args.get('numberID')
    
    if not files_str:
        return redirect(url_for('index'))
        
    generated_files = files_str.split(',')
    
    # Cria a lista de dicionários para uso no template Jinja
    files_data = [{'name': f, 'url': url_for('download_file', filename=f)} for f in generated_files]

    return render_template('result.html', files_data=files_data, numberID=numberID)

@app.route('/download/<filename>')
def download_file(filename):
    """Rota para servir os arquivos para download."""
    # send_from_directory é a maneira segura de servir arquivos estáticos dinâmicos
    return send_from_directory(app.config['ICON_FOLDER'], filename, as_attachment=True)


if __name__ == '__main__':
    # Este é o ponto de entrada que inicia o servidor web Flask
    # 'debug=True' recarrega o servidor automaticamente quando o código muda
    app.run(debug=True)