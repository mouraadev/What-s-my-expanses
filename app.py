import os
import datetime
import pytz
import sqlite3
import json
import pandas as pd
from flask import Flask, request, send_file
from twilio.twiml.messaging_response import MessagingResponse
from together import Together
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

client = Together(api_key=os.getenv("TOGETHER_API_KEY"))

conversa_ativa = {}

def init_db():
    conn = sqlite3.connect('gastos.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            item TEXT,
            valor REAL,
            categoria TEXT,
            pagamento TEXT,
            data TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def salvar_no_banco(user_id, dados_json):
    try:
        conn = sqlite3.connect('gastos.db')
        cursor = conn.cursor()

        fuso_brasil = pytz.timezone('America/Sao_Paulo')
        data_atual = datetime.datetime.now(fuso_brasil).strftime("%m-%d %H")

        cursor.execute('''
            INSERT INTO transacoes (user_id, item, valor, categoria, pagamento, data)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, dados_json['item'], dados_json['valor'], dados_json['categoria'], dados_json['pagamento'], data_atual))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao salvar no banco: {e}")
        return False

def gerar_planilha(user_id):
    """Gera um Excel com os gastos do usuário."""
    conn = sqlite3.connect('gastos.db')
    
    # Lê os dados do banco para o Pandas
    query = f"SELECT data, item, categoria, pagamento, valor FROM transacoes WHERE user_id = '{user_id}'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return None

    total = df['valor'].sum()
    linha_total = pd.DataFrame([['', '', '', 'TOTAL MENSAL', total]], columns=df.columns)
    df = pd.concat([df, linha_total], ignore_index=True)

    nome_arquivo = f"extrato_{user_id}.xlsx"
    df.to_excel(nome_arquivo, index=False)
    
    return nome_arquivo

def obter_contexto_temporal(user_id):
    """
    Define se é inicio de conversa ou continuação.
    """
    fuso_brasil = pytz.timezone('America/Sao_Paulo')
    agora = datetime.datetime.now(fuso_brasil)
    
    ultima_vez = conversa_ativa.get(user_id)
    conversa_ativa[user_id] = agora 

    hora = agora.hour
    if 5 <= hora < 12:
        saudacao_tempo = "Bom dia"
    elif 12 <= hora < 18:
        saudacao_tempo = "Boa tarde"
    else:
        saudacao_tempo = "Boa noite"

    if ultima_vez and (agora - ultima_vez).total_seconds() < 600:
        return {
            "saudacao": saudacao_tempo,
            "tipo": "CONTINUACAO", 
            "instrucao": "O usuário já está falando com você. NÃO dê Bom dia/Tarde de novo. Seja breve."
        }
    else:
        return {
            "saudacao": saudacao_tempo,
            "tipo": "INICIO", 
            "instrucao": f"Comece a frase com '{saudacao_tempo}'."
        }

def processar_mensagem(texto_usuario, user_id):
    ctx = obter_contexto_temporal(user_id)
    
    system_prompt = f"""
    Você é a F.R.I.D.A.Y., assistente financeira.
    
    IDENTIFIQUE A INTENÇÃO DO USUÁRIO:
    
    1. CUMPRIMENTO/CONVERSA: Responda educadamente.
    2. SOLICITAÇÃO DE PLANILHA/RELATÓRIO: O usuário quer ver os gastos. Responda APENAS com a palavra chave: "CMD_GERAR_RELATORIO".
    3. REGISTRO DE GASTO: O usuário informou uma compra.
       - Extraia: Item, Valor (número), Categoria (ex: Mercado, Lazer), Forma de Pagamento (ex: Pix, Crédito).
       - Se faltar a forma de pagamento, assuma "Não informado".
       - NO FINAL DA RESPOSTA, insira um bloco JSON oculto EXATAMENTE assim:
         ###JSON###{{"item": "...", "valor": 0.00, "categoria": "...", "pagamento": "..."}}###END###
    
    Contexto: {ctx['saudacao']}.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": texto_usuario}
    ]

    try:
        response = client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo", 
            messages=messages,
            temperature=0.1, 
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Erro no sistema: {str(e)}"

@app.route("/webhook", methods=['POST'])
def bot():
    msg_usuario = request.values.get('Body', '')
    user_id = request.values.get('From', 'desconhecido').replace('whatsapp:', '') # Limpa o ID
    
    print(f"Mensagem de {user_id}: {msg_usuario}")

    resposta_ia = processar_mensagem(msg_usuario, user_id)
    
    resp = MessagingResponse()
    msg = resp.message()

    if "CMD_GERAR_RELATORIO" in resposta_ia:
        arquivo = gerar_planilha(user_id)
        if arquivo:
            msg.body("Aqui está a sua planilha com o total do mês! 📊")
    
            print(f"Arquivo gerado: {arquivo}") 
        else:
            msg.body("Você ainda não tem gastos registrados para gerar planilha.")
            
    elif "###JSON###" in resposta_ia:
        try:
            texto_amigavel = resposta_ia.split("###JSON###")[0]
            json_str = resposta_ia.split("###JSON###")[1].split("###END###")[0]
            
            dados = json.loads(json_str)
            salvou = salvar_no_banco(user_id, dados)
            
            if salvou:
                msg.body(f"{texto_amigavel}\n✅ *Salvo no banco de dados!*")
            else:
                msg.body(f"{texto_amigavel}\n❌ Erro ao salvar.")
        except:
             msg.body(resposta_ia) 
             
    else:
        msg.body(resposta_ia)

    return str(resp)

if __name__ == "__main__":
    app.run(port=5000, debug=True)