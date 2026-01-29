import torch
import torch.nn as nn
import torch.nn.functional as F
import laion_clap

class ClapConditioner(nn.Module):
    def __init__(
        self,
        clap_ckpt: str,
        device: torch.device,
        use_audio: bool = True,
        use_text: bool = True,
        fusion: str = "mean",   # "mean" ou "concat"
        out_dim: int = 512
    ):
        super().__init__()

        assert use_audio or use_text, "CLAP needs audio and/or text"

        self.use_audio = use_audio
        self.use_text = use_text
        self.fusion = fusion
        self.out_dim = out_dim

        # --- Load CLAP ---
        self.clap = laion_clap.CLAP_Module(
            enable_fusion=False,
            amodel="HTSAT-base"
        )
        self.clap.load_ckpt(clap_ckpt)
        self.clap.to(device)
        self.clap.eval()

        # Freeze CLAP
        for p in self.clap.parameters():
            p.requires_grad = False

        # Optional projection if concat
        if fusion == "concat":
            in_dim = 0
            if use_audio:
                in_dim += out_dim
            if use_text:
                in_dim += out_dim

            self.proj = nn.Sequential(
                nn.Linear(in_dim, out_dim),
                nn.ReLU(),
                nn.Linear(out_dim, out_dim)
            )
        else:
            self.proj = None


    @torch.no_grad()
    def forward(self, audio_ref=None, text=None):
        """
        audio_ref: Tensor [B, T] (mono waveform)
        text: List[str] of length B

        returns:
            z_clap: Tensor [B, D_clap]
        """

        embeddings = []

        if self.use_audio:
            assert audio_ref is not None, "audio_ref is required"
            z_audio = self.clap.get_audio_embedding_from_data(
                audio_ref, use_tensor=True
            )  # [B, D_clap]
            z_audio = F.normalize(z_audio, dim=-1)
            embeddings.append(z_audio)

        if self.use_text:
            assert text is not None, "text is required"
            z_text = self.clap.get_text_embedding(
                text, use_tensor=True
            )  # [B, D_clap]
            z_text = F.normalize(z_text, dim=-1)
            embeddings.append(z_text)

        if len(embeddings) == 1:
            z = embeddings[0]
        else:
            if self.fusion == "mean":
                z = torch.stack(embeddings, dim=0).mean(dim=0)
            elif self.fusion == "concat":
                z = torch.cat(embeddings, dim=-1)
                z = self.proj(z)
            else:
                raise ValueError(f"Unknown fusion mode {self.fusion}")

        z = F.normalize(z, dim=-1)
        return z
