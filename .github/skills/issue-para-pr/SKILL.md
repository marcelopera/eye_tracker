---
name: issue-para-pr
description: Implemente uma issue aberta deste repositório em uma branch criada a partir da main atualizada e abra um pull request. Use quando o usuário pedir para trabalhar em uma issue seguindo esse fluxo.
---

# Da issue ao pull request

1. Identifique a issue aberta indicada pelo usuário e leia sua descrição e os comentários relevantes. Se não houver uma issue indicada e houver várias candidatas, peça ao usuário que escolha; se houver apenas uma, use-a. Esclareça requisitos que impeçam a implementação.
2. Verifique o estado do Git e preserve alterações existentes. Busque a `main` mais recente do remoto e crie uma branch específica para a issue a partir de `origin/main`, sem descartar trabalho local nem alterar a branch atual à força. Por exemplo, para a issue 42, use `issue/42-descricao-curta`. Se mudanças locais impedirem a troca, mantenha-as intactas e use uma worktree isolada ou peça orientação.
3. Implemente o escopo da issue, seguindo as instruções do repositório. Execute as verificações apropriadas e corrija falhas relacionadas. Se houver bloqueio externo ou falha preexistente, registre-o com clareza.
4. Revise o diff, crie um commit apenas com as alterações pertinentes e publique a branch. Abra um pull request para `main`, usando o fluxo de PR disponível no ambiente. Descreva o problema, a solução e as verificações realizadas; inclua `Closes #42` com o número real da issue.
5. Informe o link do PR, os testes e quaisquer limitações. Acompanhe as verificações do PR e corrija falhas relacionadas até terminarem, quando o acesso permitir. Não faça merge nem feche manualmente a issue, salvo pedido do usuário.
