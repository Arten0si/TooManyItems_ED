# TMI3 – tworzenie przedmiotu przez funkcje gry (z egzemplarzem PIDE)
# Hook na wejsciu enshrouded.exe+411DF0 (wypelnianie transakcji ekwipunku):
#   rcx = transakcja gry, rdx = referencje (0xF0 B, +8 = swiat)
# Gdy REQ==1 i swiat == WORLD: wlasna transakcja na watku gry:
#   CTOR(tx); INIT(tx,refs); info=LOOKUP(item, tx+8);
#   CREATE(&out, tx, slotRef, info, qty, &optA, &optB, &optC); COMMIT/ROLLBACK; DTOR
        .intel_syntax noprefix
        .text
        .set B, 0                     # adresy wzgledem poczatku bloku
        .org 0x200
start:
        cmp dword ptr [rip+blk+0x18], 1        # REQ
        jne orig
        push rax
        mov rax, [rdx+8]
        cmp rax, [rip+blk+0x10]                # WORLD
        jne skip
        push rcx
        mov eax, 1
        mov ecx, 2
        lock cmpxchg dword ptr [rip+blk+0x18], ecx
        pop rcx
        jne skip
        pop rax
        push rax
        push rcx
        push rdx
        push rbx
        push rbp
        push rsi
        push rdi
        push r8
        push r9
        push r10
        push r11
        push r12
        push r13
        push r14
        push r15
        pushfq
        lock inc dword ptr [rip+blk+0x34]      # HITS
        mov rbp, rsp
        and rsp, -16
        sub rsp, 0x60
        cld
        mov rsi, rdx                            # kopia referencji gry
        lea rdi, [rip+blk+0x100]
        mov ecx, 0x1e
        rep movsq
        lea rcx, [rip+blk+0x1000]
        call qword ptr [rip+blk+0x40]          # CTOR
        lea rcx, [rip+blk+0x1000]
        lea rdx, [rip+blk+0x100]
        call body                               # INIT (oryginalna +411DF0)
        mov ecx, dword ptr [rip+blk+0x28]      # ITEM
        mov rdx, [rip+blk+0x1008]              # tx+8 = baza przedmiotow
        call qword ptr [rip+blk+0x48]          # LOOKUP
        test rax, rax
        jz nofind
        mov r9, rax
        movzx r8d, byte ptr [rip+blk+0x24]     # SLOT
        shl r8, 32
        mov eax, dword ptr [rip+blk+0x20]      # HANDLE
        or r8, rax                              # slotRef
        mov eax, dword ptr [rip+blk+0x2c]      # QTY
        mov [rsp+0x20], rax
        lea rax, [rip+blk+0x90]
        mov [rsp+0x28], rax
        lea rax, [rip+blk+0xa0]
        mov [rsp+0x30], rax
        lea rax, [rip+blk+0xb0]
        mov [rsp+0x38], rax
        lea rcx, [rip+blk+0x80]                # OUT
        lea rdx, [rip+blk+0x1000]
        call qword ptr [rip+blk+0x58]          # CREATE
        movzx eax, byte ptr [rip+blk+0x80]
        mov dword ptr [rip+blk+0x1c], eax      # RESULT
        mov eax, dword ptr [rip+blk+0x88]
        mov dword ptr [rip+blk+0x30], eax      # LEFT
        cmp byte ptr [rip+blk+0x80], 0
        jne rollback
        lea rcx, [rip+blk+0x1000]
        call qword ptr [rip+blk+0x60]          # COMMIT
        jmp dtor
nofind:
        mov dword ptr [rip+blk+0x1c], 0x100
rollback:
        lea rcx, [rip+blk+0x1000]
        call qword ptr [rip+blk+0x68]          # ROLLBACK
dtor:
        lea rcx, [rip+blk+0x1000]
        call qword ptr [rip+blk+0x70]          # DTOR
        lock inc dword ptr [rip+blk+0x38]      # DONE
        mov dword ptr [rip+blk+0x18], 3        # REQ = gotowe
        mov rsp, rbp
        popfq
        pop r15
        pop r14
        pop r13
        pop r12
        pop r11
        pop r10
        pop r9
        pop r8
        pop rdi
        pop rsi
        pop rbp
        pop rbx
        pop rdx
        pop rcx
        pop rax
        jmp orig
skip:
        pop rax
orig:
body:
        mov byte ptr [rcx+0x71a8], 0
        jmp qword ptr [rip+blk+0x8]            # RET = +411DF7
        .set blk, start-0x200
