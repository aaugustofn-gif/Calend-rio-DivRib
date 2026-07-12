# Calendário de Atividades — OM

## O que este projeto faz
Calendário coletivo (sem login) para lançar e consultar eventos/atividades da OM,
com cores por tipo, status automático (com opção de ajuste manual) e exportação
em PDF de um período escolhido.

## Passo a passo (mesmo fluxo dos outros projetos)

1. **TiDB Cloud**: crie um cluster gratuito (ou reaproveite um existente, mas
   recomendo um banco novo só para este projeto). Anote host, usuário, senha
   e nome do banco.
2. **GitHub**: crie um repositório novo e envie estes arquivos pelo navegador
   (Add file → Upload files). Mantenha a estrutura de pastas exatamente como está
   (`templates/` e `static/` precisam ser subpastas).
3. **Render**: New → Web Service → conecte o repositório.
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Em Environment, adicione a variável `DATABASE_URL` (veja o formato em
     `.env.example`, usando os dados do seu cluster TiDB).
4. As tabelas são criadas automaticamente na primeira vez que a aplicação sobe
   (não precisa rodar nenhum comando de migração).
5. Ao abrir o site pela primeira vez, cadastre os tipos de evento (botão
   "Tipos de Evento") antes de lançar o primeiro evento — cada evento precisa
   de um tipo já existente.

## Observação de segurança
Lembre-se de nunca colar a `DATABASE_URL` (nem nenhuma credencial) em campos
de chat, apenas no painel de Environment do Render.
