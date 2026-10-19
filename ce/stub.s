.intel_syntax noprefix
.text
.globl blk
blk:
magic:   .ascii "TMI1hook"          # 0x000
fnaddr:  .quad 0                    # 0x008  enshrouded.exe+225B70
retaddr: .quad 0                    # 0x010  hook+6
target:  .quad 0                    # 0x018  adres rzędu do odświeżenia
request: .byte 0                    # 0x020
         .byte 0,0,0,0,0,0,0
done:    .long 0                    # 0x028
hits:    .long 0                    # 0x02C
         .quad 0                    # 0x030
         .quad 0                    # 0x038
table:                              # 0x040: 64 x {row(8), ctx(8), handle(4), pad(4)}
         .fill 64*24,1,0
.org 0x700
entry:
    push rdi                        # [rsp] = ctx (oryginalne rdi)
    mov  rdi, [rax]                 # oryginalna instrukcja
    push rax
    push rcx
    push rdx
    lea  rcx, [rip+table]
    mov  edx, 64
1:
    mov  rax, [rcx]
    test rax, rax
    jz   2f
    cmp  rax, rdi
    je   3f
    add  rcx, 24
    dec  edx
    jnz  1b
    jmp  3f
2:
    mov  [rcx], rdi
    mov  rax, [rsp+24]              # ctx
    mov  [rcx+8], rax
    mov  [rcx+16], ebx
3:
    pop  rdx
    pop  rcx
    pop  rax
    cmp  rdi, [rip+target]
    jne  9f
    lock inc dword ptr [rip+hits]
    push rax
    xor  eax, eax
    xchg al, byte ptr [rip+request]
    cmp  al, 1
    pop  rax
    jne  9f
    push rax
    push rcx
    push rdx
    push r8
    push r9
    push r10
    push r11
    push rbp
    mov  rbp, rsp
    and  rsp, -16
    sub  rsp, 0x20
    mov  rcx, [rbp+0x40]            # ctx (push rdi na wejściu)
    mov  rdx, [rbp+0x238]           # typ komponentu = [rsp_oryg+0x1F0]
    mov  r8d, ebx                   # uchwyt rzędu
    mov  rax, [rip+fnaddr]
    call rax
    lock inc dword ptr [rip+done]
    mov  rsp, rbp
    pop  rbp
    pop  r11
    pop  r10
    pop  r9
    pop  r8
    pop  rdx
    pop  rcx
    pop  rax
9:
    add  rsp, 8                     # zdejmij zapisane rdi
    test rdi, rdi                   # oryginalna instrukcja
    jmp  qword ptr [rip+retaddr]
end:
