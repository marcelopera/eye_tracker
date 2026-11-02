# Ambiente Windows e laboratório

O servidor ainda não foi implementado. Estas são orientações de preparação, não uma instalação funcional.

- Instale Docker Desktop e habilite WSL2. Ajuste a memória conforme a máquina e a carga; exemplo em `%UserProfile%\.wslconfig` (reinicie WSL após a alteração com `wsl --shutdown`):

  ```ini
  [wsl2]
  memory=8GB
  ```

  O valor é exemplo, não requisito medido. Mantenha volumes de trabalho no sistema ext4 da distribuição WSL, evitando `/mnt/c` para dados ativos. Proteja o disco e os backups.
- Prefira roteador dedicado, servidor conectado por cabo e celular na mesma LAN; redes institucionais podem isolar clientes. Uma reserva DHCP evita mudanças do IP do servidor. Confirme conectividade e aplique regras de firewall restritas à rede de laboratório e às portas efetivamente escolhidas. Ainda não há portas definidas neste projeto.
- Para TLS local, crie CA e certificado com ferramentas como mkcert incluindo o nome/IP do servidor no certificado; proteja a chave privada da CA. Instale a confiança necessária no PC e, quando houver cliente de rede, configure explicitamente a confiança da CA no Android com `network_security_config`. Não desative validação TLS nem distribua a chave privada. As regras de confiança diferem conforme o cliente e a versão Android; teste no dispositivo.
- Verifique Docker, endereço LAN e `adb devices` na máquina de coleta. Confira manualmente a regra de firewall e portas ao definir os serviços; não existem regras prontas no repositório.
