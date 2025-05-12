#!/usr/bin/env python3
"""
This script validates and fixes the MongoDB URI format.
Run this script to check if your MongoDB URI is correctly formatted.
"""
import os
import re
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def validate_mongo_uri(uri):
    """Validate and fix MongoDB URI format"""
    if not uri:
        print("ERROR: MONGO_URI is not set in environment variables")
        return None
        
    # Check if URI follows the correct format
    # Should be: mongodb+srv://username:password@cluster.host.mongodb.net/
    # or: mongodb://username:password@host:port/
    
    # Common format errors:
    # 1. Double @ symbol: mongodb+srv://username:password@username:password@cluster.host
    # 2. Format with username-password in wrong place: mongodb+srv://username@password:cluster
    
    # Mask URI for safe printing
    masked_uri = re.sub(r'(mongodb(\+srv)?://)[^@:]+:[^@]+(@)', r'\1***:***\3', uri)
    print(f"Checking URI: {masked_uri}")
    
    # Basic pattern validation
    srv_pattern = r'^mongodb\+srv://[^:]+:[^@]+@[^/]+(/.*)?$'
    standard_pattern = r'^mongodb://[^:]+:[^@]+@[^/]+(:\d+)?(/.*)?$'
    
    if re.match(srv_pattern, uri) or re.match(standard_pattern, uri):
        print("URI format appears to be valid.")
        return uri
    
    # Try to fix common issues
    # Check for double @ symbol (username:password@username:password@)
    double_at_match = re.search(r'(://[^@]+)@([^@:]+:[^@]+@)', uri)
    if double_at_match:
        print("Found double @ symbol pattern in URI. Fixing...")
        corrected_uri = uri.replace(double_at_match.group(0), double_at_match.group(1))
        
        # Mask corrected URI for safe printing
        masked_corrected = re.sub(r'(mongodb(\+srv)?://)[^@:]+:[^@]+(@)', r'\1***:***\3', corrected_uri)
        print(f"Corrected URI: {masked_corrected}")
        return corrected_uri
    
    # Check for other common patterns that need fixing
    # This could be expanded based on specific format errors
    
    print("Could not automatically fix the URI format. Please check your MongoDB connection string.")
    return uri

def main():
    """Main function to validate and fix MongoDB URI"""
    uri = os.getenv("MONGO_URI")
    fixed_uri = validate_mongo_uri(uri)
    
    if fixed_uri and fixed_uri != uri:
        print("\nThe URI format has been fixed. You should update your .env file with the corrected URI.")
        print("For security reasons, we don't automatically update your .env file.")
        
        # Output instructions
        print("\nTo update, replace your current MONGO_URI with:")
        print(f"MONGO_URI={fixed_uri}")
    
    # Check for other MongoDB URI parameters
    if fixed_uri and "retryWrites=true" not in fixed_uri:
        print("\nTIP: Consider adding 'retryWrites=true' to your URI for better connection reliability.")
    
    if fixed_uri and "w=majority" not in fixed_uri:
        print("TIP: Consider adding 'w=majority' to your URI for better write consistency.")
    
    print("\nRemember to keep your MongoDB credentials secure!")

if __name__ == "__main__":
    main() 