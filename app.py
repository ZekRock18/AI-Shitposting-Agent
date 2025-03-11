import os
import json
import requests
import streamlit as st
import time

# --------------------------------------
# Configuration and Setup
# --------------------------------------
# Get your secret keys from Streamlit secrets
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
APTOS_PRIVATE_KEY = st.secrets["APTOS_PRIVATE_KEY"]
MODULE_ADDRESS = st.secrets["MODULE_ADDRESS"]
APTOS_NODE_URL = st.secrets["APTOS_NODE_URL"]

# --------------------------------------
# Helper Functions
# --------------------------------------
def get_trending_topics():
    """
    Use Groq to determine current trending topics instead of Twitter API
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "What are the top 10 trending topics on the internet right now? Just list them as hashtags, no explanations (e.g. #Crypto, #AI, etc). Be specific about current trends."
            }
        ],
        "model": "qwen-2.5-32b",
        "max_tokens": 150,
        "temperature": 0.2,
        "top_p": 1
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            topics_text = data["choices"][0]["message"]["content"].strip()
            
            # Process the response to extract hashtags
            topics = [topic.strip() for topic in topics_text.split(",")]
            # Ensure each topic has a hashtag
            topics = [topic if topic.startswith("#") else f"#{topic}" for topic in topics]
            
            return topics
        else:
            st.warning(f"Could not fetch trends from Groq. Status code: {response.status_code}")
            return ["#Crypto", "#Aptos", "#Web3", "#AI", "#Blockchain", "#NFTs"]
    except Exception as e:
        st.error("Error fetching trends: " + str(e))
        return ["#Crypto", "#Aptos", "#Web3", "#AI", "#Blockchain", "#NFTs"]

def groq_generate_post(topic):
    """
    Generate a witty post about the given topic using the Groq API.
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    payload = {
        "messages": [
            {
                "role": "user",
                "content": f"Generate a witty, irreverent, and humorous post about {topic} in the style of popular internet shitposts. Keep it under 280 characters."
            }
        ],
        "model": "mistral-saba-24b",
        "max_tokens": 100,
        "temperature": 0.9,
        "top_p": 1
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Extract the text from the Groq response
            return data["choices"][0]["message"]["content"].strip()
        else:
            return f"Error from Groq API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Exception when calling Groq API: {e}"

def record_post_to_blockchain(post_text):
    """
    Record the generated post on-chain using Aptos REST API
    with proper transaction signing and submission.
    """
    try:
        if not APTOS_PRIVATE_KEY or not MODULE_ADDRESS:
            st.warning("Missing Aptos configuration. Please set APTOS_PRIVATE_KEY and MODULE_ADDRESS.")
            return None
            
        # 1. Get account information and current sequence number
        account_url = f"{APTOS_NODE_URL}/accounts/{MODULE_ADDRESS}"
        account_response = requests.get(account_url)
        
        if account_response.status_code != 200:
            st.error(f"Failed to get account info: {account_response.text}")
            st.info("Make sure your account exists on testnet and has been funded.")
            st.markdown("[Fund your testnet account here](https://aptoslabs.com/testnet-faucet)")
            return None
            
        account_data = account_response.json()
        sequence_number = int(account_data.get("sequence_number", "0"))
        
        # Display account info for debugging
        st.info(f"Account found on testnet. Sequence number: {sequence_number}")
        
        # 2. Prepare transaction payload
        module_name = "shitpost_logger"
        function_name = "log_post"
        
        # Convert string to bytes for the Move function
        post_bytes = [ord(c) for c in post_text]
        
        current_time = int(time.time()) + 600  # 10 minutes expiration
        
        payload = {
            "sender": MODULE_ADDRESS,
            "sequence_number": str(sequence_number),
            "max_gas_amount": "5000",  # Increased gas limit for testnet
            "gas_unit_price": "100",
            "expiration_timestamp_secs": str(current_time),
            "payload": {
                "type": "entry_function_payload",
                "function": f"{MODULE_ADDRESS}::{module_name}::{function_name}",
                "type_arguments": [],
                "arguments": [post_bytes]
            }
        }
        
        # 3. Submit transaction for signing
        tx_url = f"{APTOS_NODE_URL}/transactions/encode_submission"
        tx_response = requests.post(tx_url, json=payload)
        
        if tx_response.status_code != 200:
            st.error(f"Failed to encode transaction: {tx_response.text}")
            
            # Check if it's a module not found error
            error_text = tx_response.text
            if "cannot resolve module" in error_text.lower() or "module not found" in error_text.lower():
                st.warning(f"The module '{module_name}' might not be deployed at address {MODULE_ADDRESS}.")
                st.info("Make sure you've deployed your Move module to this account on testnet.")
            
            return None
            
        encoded_submission = tx_response.json()
        
        # 4. Sign transaction
        # Note: In a production app, you'd use proper signing libraries
        # This is simplified for demonstration purposes
        try:
            from nacl.signing import SigningKey
            import base64
        except ImportError:
            st.error("PyNaCl library is required for transaction signing. Install with: pip install pynacl")
            return None
            
        # Convert hex private key to bytes
        private_key_bytes = bytes.fromhex(APTOS_PRIVATE_KEY.replace("0x", ""))
        signing_key = SigningKey(private_key_bytes)
        
        # Sign the message
        signature = signing_key.sign(bytes.fromhex(encoded_submission))
        signature_hex = signature.signature.hex()
        
        # 5. Submit signed transaction
        signed_tx = {
            "sender": MODULE_ADDRESS,
            "sequence_number": str(sequence_number),
            "max_gas_amount": "5000",  # Increased gas limit for testnet
            "gas_unit_price": "100",
            "expiration_timestamp_secs": str(current_time),
            "payload": payload["payload"],
            "signature": {
                "type": "ed25519_signature",
                "public_key": signing_key.verify_key.encode(encoder=base64.b64encode).decode("utf-8"),
                "signature": base64.b64encode(bytes.fromhex(signature_hex)).decode("utf-8")
            }
        }
        
        submit_url = f"{APTOS_NODE_URL}/transactions"
        submit_response = requests.post(submit_url, json=signed_tx)
        
        if submit_response.status_code == 202:
            tx_data = submit_response.json()
            tx_hash = tx_data.get("hash")
            st.success("Transaction submitted successfully!")
            return tx_hash
        else:
            st.error(f"Failed to submit transaction: {submit_response.text}")
            return None
            
    except Exception as e:
        st.error(f"Blockchain transaction error: {e}")
        return None

# --------------------------------------
# Streamlit Frontend
# --------------------------------------
def main():
    st.title("Shitposting Assistant with Aptos & Move AI Agents")
    st.write("This tool uses Groq to generate a funny post based on trending topics and records the post on-chain via the Aptos testnet.")
    
    # Network info
    st.info("🌐 Currently using **Aptos Testnet**")

    # Get trending topics from Groq analysis
    with st.spinner("Fetching trending topics..."):
        trending_topics = get_trending_topics()
    
    # Allow custom topic input
    use_custom = st.checkbox("Enter your own topic")
    
    if use_custom:
        topic = st.text_input("Enter a topic:")
    else:
        topic = st.selectbox("Choose a trending topic:", trending_topics)
    
    record_option = st.checkbox("Record generated post on Aptos blockchain")

    # Additional options for blockchain recording
    if record_option:
        st.write("### Blockchain Configuration")
        st.markdown(f"**Account Address**: `{MODULE_ADDRESS}`")
        module_name = st.text_input("Module Name", "shitpost_logger")
        function_name = st.text_input("Function Name", "log_post")
        
        # Help text about Move module
        with st.expander("About the Move Module"):
            st.markdown("""
            Your Move module should have a function with this signature:
            ```move
            public entry fun log_post(account: &signer, post_text: vector<u8>) {
                // Your implementation here
            }
            ```
            
            Make sure the module is deployed to your account on the testnet.
            """)

    if st.button("Generate Post"):
        if not topic:
            st.warning("Please enter a topic")
            return
            
        with st.spinner("Generating post..."):
            generated_post = groq_generate_post(topic)
        
        st.subheader("Generated Post:")
        st.markdown(f"**Topic**: {topic}")
        st.write(generated_post)
        
        if record_option:
            with st.spinner("Recording post on Aptos blockchain..."):
                tx_hash = record_post_to_blockchain(generated_post)
                
            if tx_hash:
                st.success(f"Post recorded on-chain! Transaction Hash: {tx_hash}")
                st.markdown(f"[View on Aptos Explorer](https://explorer.aptoslabs.com/txn/{tx_hash}?network=testnet)")
            else:
                st.error("Failed to record post on blockchain. Check logs for details.")

if __name__ == '__main__':
    main()
