# X post 1 — attach the PNG

Where Ward fits in draft XLS-66:

Evidence → fixed policy → resolution record + unsigned LoanManage → Loan Broker reviews/signs → XRPL applies the transition.

Ward is an application-layer control. It never signs or submits.

ward_signed = False — always.

# X reply 2 — source and boundary

Architecture note: Ward does not modify rippled or XLS-66. It prepares an evidence-bound resolution record; the authorized Loan Broker retains execution authority.

Official XLS-66 source:
https://github.com/XRPLF/XRPL-Standards/tree/master/XLS-0066-lending-protocol

# Alt text

Ward architecture diagram titled "The XLS-66 default lifecycle." Four stages run left to right: a default condition is observed from authoritative evidence; Ward evaluates fixed policy and prepares a replayable resolution record with an unsigned LoanManage instruction; the Loan Broker reviews, approves or rejects, and signs through its own controls; XRPL validates authorization and applies the protocol state transition. A boundary line states that Ward has no custody, no signing authority, and requires no rippled modification. The footer reads "ward_signed = False — always."

# Suggested filename

ward-xls66-default-lifecycle.png
