"""
Script de diagnostic manuel de la configuration Groq (Partie 2, legacy).
Ce n'est pas une suite pytest : lance-le directement avec
`python check_groq_config.py` pour un rapport lisible en console.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# TEST 1 : CONFIGURATION
# ============================================================================

def test_config():
    print("\n" + "=" * 60)
    print("TEST 1 - CONFIGURATION GROQ")
    print("=" * 60)

    api_key = os.getenv("GROQ_API_KEY")

    if api_key and api_key != "your_groq_api_key_here":
        print("✅ GROQ_API_KEY configurée")
        print(f"   Clé: {api_key[:10]}...{api_key[-5:]}")
    else:
        print("❌ GROQ_API_KEY manquante ou invalide")
        return False

    print("✅ Variables d'environnement:")
    print(f"   HOST: {os.getenv('API_HOST', '0.0.0.0')}")
    print(f"   PORT: {os.getenv('API_PORT', '8000')}")
    print(f"   MODEL: {os.getenv('LLM_MODEL', 'llama-3.3-70b-versatile')}")
    print(f"   TEMPERATURE: {os.getenv('LLM_TEMPERATURE', '0.7')}")

    return True


# ============================================================================
# TEST 2 : IMPORT
# ============================================================================

async def test_import():
    print("\n" + "=" * 60)
    print("TEST 2 - IMPORT MODULE GROQ")
    print("=" * 60)

    try:
        print("✅ Module llm_groq importé")
        return True

    except Exception as e:
        print(f"❌ Erreur import: {e}")
        return False


# ============================================================================
# TEST 3 : CLIENT
# ============================================================================

async def test_client():
    print("\n" + "=" * 60)
    print("TEST 3 - CLIENT GROQ")
    print("=" * 60)

    try:
        from llm_groq import GroqLLM

        api_key = os.getenv("GROQ_API_KEY")

        if not api_key or api_key == "your_groq_api_key_here":
            print("⚠️ GROQ_API_KEY manquante")
            return False

        client = GroqLLM()

        print("✅ Client Groq créé")
        print(f"   Modèle: {client.config.model}")
        print(f"   Température: {client.config.temperature}")
        print(f"   Max tokens: {client.config.max_tokens}")

        return True

    except Exception as e:
        print(f"❌ Erreur client: {e}")
        return False


# ============================================================================
# TEST 4 : GÉNÉRATION
# ============================================================================

async def test_generation():
    print("\n" + "=" * 60)
    print("TEST 4 - GÉNÉRATION GROQ")
    print("=" * 60)

    try:
        from llm_groq import GroqLLM

        api_key = os.getenv("GROQ_API_KEY")

        if not api_key or api_key == "your_groq_api_key_here":
            print("⚠️ GROQ_API_KEY manquante")
            return False

        client = GroqLLM()

        print("⏳ Génération en cours avec Groq...")

        response = await client.generate_response(
            "Recommande un film d'horreur classique en une phrase"
        )

        print("✅ Réponse générée")
        print(f"   Taille: {len(response)} caractères")
        print(f"   Réponse: {response[:200]}")

        return True

    except Exception as e:
        print(f"❌ Erreur génération: {e}")
        return False


# ============================================================================
# MAIN
# ============================================================================

async def main():

    results = []

    results.append(("Configuration Groq", test_config()))
    results.append(("Import module", await test_import()))
    results.append(("Client Groq", await test_client()))
    results.append(("Génération", await test_generation()))

    print("\n" + "=" * 60)
    print("RÉSUMÉ FINAL GROQ")
    print("=" * 60)

    for name, ok in results:
        print(f"{'✅' if ok else '❌'} {name}")

    success = all(r for _, r in results)

    print("=" * 60)

    if success:
        print("🎉 TOUS LES TESTS GROQ SONT PASSÉS")
        print("👉 API prête à être lancée")
    else:
        print("⚠️ CERTAINS TESTS ONT ÉCHOUÉ")
        print("👉 Vérifie GROQ_API_KEY et dépendances")

    return success


# ============================================================================
# EXECUTION
# ============================================================================

if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)