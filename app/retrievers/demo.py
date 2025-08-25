import weaviate
from langchain.schema import Document
from langchain_weaviate import WeaviateVectorStore
from langchain_ollama import OllamaEmbeddings


def main():
    # Initialize Ollama embeddings (make sure the model is pulled first)
    embeddings = OllamaEmbeddings(model="nomic-embed-text")

    # Connect to local Weaviate
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url="rflcvk6slu7i1dqqhjtfw.c0.asia-southeast1.gcp.weaviate.cloud",
        auth_credentials=weaviate.classes.init.Auth.api_key("WUFyMHdaS2dybTJzZWlKa19kUmRZOVRpWWhKdGl0RHB2aWM2V0RLTTRXY2xVV2t2MWx5WWNKT0N4dlprPV92MjAw"),
    )
    try:
        print("Weaviate ready?", client.is_ready())

        vectorstore = WeaviateVectorStore(
            client=client,
            index_name="FAQ",
            text_key="text",
            embedding=embeddings,
        )

        # Sample FAQ docs
        raw_documents = [
        {"id": "doc1", "title": "Return Policy", "content": "You can return items within 30 days of purchase. Refunds are processed within 5 business days."},
        {"id": "doc2", "title": "Shipping Policy", "content": "We ship to over 50 countries. Delivery takes 5-10 business days depending on the location."},
        {"id": "doc3", "title": "Payment Methods", "content": "We accept Visa, Mastercard, PayPal, and Apple Pay."},
        {"id": "doc4", "title": "Account Creation", "content": "Creating an account allows you to track orders and save your wishlist."},
        {"id": "doc5", "title": "Customer Support", "content": "Our customer support is available 24/7 via chat and email."},
        {"id": "doc6", "title": "Privacy Policy", "content": "We protect your personal information and never share it with third parties without consent."},
        {"id": "doc7", "title": "Warranty Information", "content": "All products come with a 1-year manufacturer warranty covering defects."},
        {"id": "doc8", "title": "Order Tracking", "content": "Track your order status in real-time through your account dashboard."},
        {"id": "doc9", "title": "International Shipping", "content": "Additional customs fees may apply for international orders."},
        {"id": "doc10", "title": "Gift Cards", "content": "Gift cards never expire and can be used for any purchase on our site."},
        {"id": "doc11", "title": "Price Match Guarantee", "content": "We'll match any competitor's price within 14 days of purchase."},
        {"id": "doc12", "title": "Product Availability", "content": "Items marked 'In Stock' ship within 24 hours. Backorders take 2-3 weeks."},
        {"id": "doc13", "title": "Secure Shopping", "content": "Our website uses 256-bit SSL encryption to protect your data."},
        {"id": "doc14", "title": "Newsletter Subscription", "content": "Subscribe to get 10% off your first order and exclusive deals."},
        {"id": "doc15", "title": "Size Guide", "content": "Refer to our sizing chart for accurate measurements before ordering."},
        {"id": "doc16", "title": "Product Reviews", "content": "Share your experience by leaving a review after purchase."},
        {"id": "doc17", "title": "Order Cancellation", "content": "Cancel your order within 1 hour of placement for full refund."},
        {"id": "doc18", "title": "Business Hours", "content": "Our offices are open Monday-Friday, 9 AM to 6 PM EST."},
        {"id": "doc19", "title": "Store Locations", "content": "Visit our 25 retail locations across the United States."},
        {"id": "doc20", "title": "Mobile App", "content": "Download our app for exclusive mobile-only discounts and features."},
        {"id": "doc21", "title": "Loyalty Program", "content": "Earn points on every purchase and redeem for discounts."},
        {"id": "doc22", "title": "Bulk Orders", "content": "Contact us for special pricing on orders over 50 units."},
        {"id": "doc23", "title": "Product Care", "content": "Follow the care instructions to maintain product quality."},
        {"id": "doc24", "title": "Email Preferences", "content": "Manage your marketing email preferences in account settings."},
        {"id": "doc25", "title": "Shipping Restrictions", "content": "Some items cannot be shipped to certain countries due to regulations."},
        {"id": "doc26", "title": "Return Exceptions", "content": "Personalized items and software cannot be returned."},
        {"id": "doc27", "title": "Payment Security", "content": "We never store your credit card information on our servers."},
        {"id": "doc28", "title": "Order History", "content": "Access your complete order history in your account profile."},
        {"id": "doc29", "title": "Product Specifications", "content": "Detailed technical specifications available for each product."},
        {"id": "doc30", "title": "Contact Information", "content": "Reach us at support@company.com or 1-800-123-4567."},
        {"id": "doc31", "title": "Website Accessibility", "content": "We strive to make our website accessible to all users."},
        {"id": "doc32", "title": "Social Media", "content": "Follow us on social media for updates and promotions."},
        {"id": "doc33", "title": "Product Registration", "content": "Register your product to activate warranty and receive support."},
        {"id": "doc34", "title": "Shipping Insurance", "content": "Optional shipping insurance available for valuable items."},
        {"id": "doc35", "title": "Return Shipping", "content": "Free return shipping on all US orders over $50."},
        {"id": "doc36", "title": "Gift Wrapping", "content": "Add gift wrapping and personalized message for $5.99."},
        {"id": "doc37", "title": "Order Minimum", "content": "Minimum order of $25 required for free shipping."},
        {"id": "doc38", "title": "Product Recalls", "content": "Check this page for any active product recalls or safety notices."},
        {"id": "doc39", "title": "Account Security", "content": "Enable two-factor authentication for enhanced account security."},
        {"id": "doc40", "title": "Business Accounts", "content": "Special pricing and terms available for business customers."},
        {"id": "doc41", "title": "Product Demonstrations", "content": "Watch video demonstrations of our products in action."},
        {"id": "doc42", "title": "Shipping Notifications", "content": "Receive email and SMS notifications for shipping updates."},
        {"id": "doc43", "title": "Return Exchanges", "content": "Exchange items for different sizes or colors within 30 days."},
        {"id": "doc44", "title": "Payment Plans", "content": "Interest-free payment plans available for orders over $500."},
        {"id": "doc45", "title": "Product Compatibility", "content": "Check compatibility before purchasing accessories or add-ons."},
        {"id": "doc46", "title": "Order Editing", "content": "Edit your order within 15 minutes of placement."},
        {"id": "doc47", "title": "Shipping Speed", "content": "Express shipping delivers within 2-3 business days."},
        {"id": "doc48", "title": "Return Status", "content": "Track your return status in your account dashboard."},
        {"id": "doc49", "title": "Payment Failure", "content": "Contact your bank if payment fails due to authorization issues."},
        {"id": "doc50", "title": "Account Deletion", "content": "Request account deletion by contacting customer support."},
        {"id": "doc51", "title": "Product Updates", "content": "Receive firmware and software updates for your products."},
        {"id": "doc52", "title": "Shipping Address", "content": "Ensure shipping address is correct as changes are difficult after processing."},
        {"id": "doc53", "title": "Return Documentation", "content": "Include original invoice with all returns for faster processing."},
        {"id": "doc54", "title": "Payment Confirmation", "content": "You'll receive payment confirmation email immediately after purchase."},
        {"id": "doc55", "title": "Account Recovery", "content": "Reset password using email recovery if you forget login details."},
        {"id": "doc56", "title": "Product Testing", "content": "All products undergo rigorous quality testing before shipping."},
        {"id": "doc57", "title": "Shipping Carriers", "content": "We use FedEx, UPS, and USPS for domestic shipments."},
        {"id": "doc58", "title": "Return Exceptions", "content": "Final sale items and clearance products cannot be returned."},
        {"id": "doc59", "title": "Payment Authorization", "content": "Payments are authorized immediately but charged only upon shipment."},
        {"id": "doc60", "title": "Account Verification", "content": "Verify your email address to complete account registration."},
        {"id": "doc61", "title": "Product Materials", "content": "All product materials are listed in the description section."},
        {"id": "doc62", "title": "Shipping Delays", "content": "Weather or carrier issues may occasionally cause shipping delays."},
        {"id": "doc63", "title": "Return Refunds", "content": "Refunds are issued to original payment method within 5-7 days."},
        {"id": "doc64", "title": "Payment Methods International", "content": "International customers can pay with credit cards or PayPal."},
        {"id": "doc65", "title": "Account Benefits", "content": "Account holders get early access to sales and new products."},
        {"id": "doc66", "title": "Product Assembly", "content": "Some products require assembly - instructions included in package."},
        {"id": "doc67", "title": "Shipping Tracking", "content": "Tracking numbers are provided within 24 hours of shipment."},
        {"id": "doc68", "title": "Return Timeframe", "content": "Returns must be postmarked within 30 days of delivery date."},
        {"id": "doc69", "title": "Payment Security", "content": "All payments are PCI DSS compliant and securely processed."},
        {"id": "doc70", "title": "Account Privacy", "content": "We respect your privacy and protect your personal information."},
        {"id": "doc71", "title": "Product Warranty", "content": "Warranty covers manufacturing defects but not accidental damage."},
        {"id": "doc72", "title": "Shipping Costs", "content": "Shipping costs are calculated based on weight and destination."},
        {"id": "doc73", "title": "Return Conditions", "content": "Items must be returned in original condition with all tags attached."},
        {"id": "doc74", "title": "Payment Currency", "content": "All prices are in USD. Currency conversion fees may apply."},
        {"id": "doc75", "title": "Account Multi-Device", "content": "Access your account from multiple devices with secure login."},
        {"id": "doc76", "title": "Product Sustainability", "content": "We use eco-friendly materials and sustainable manufacturing processes."},
        {"id": "doc77", "title": "Shipping Packaging", "content": "Items are packaged securely to prevent damage during transit."},
        {"id": "doc78", "title": "Return Labels", "content": "Print return labels directly from your order details page."},
        {"id": "doc79", "title": "Payment Disputes", "content": "Contact us before disputing charges to resolve issues quickly."},
        {"id": "doc80", "title": "Account Notifications", "content": "Customize which notifications you receive in account settings."},
        {"id": "doc81", "title": "Product Innovation", "content": "We continuously improve products based on customer feedback."},
        {"id": "doc82", "title": "Shipping Options", "content": "Choose from standard, expedited, or overnight shipping options."},
        {"id": "doc83", "title": "Return Exceptions", "content": "Digital products and downloadable content cannot be returned."},
        {"id": "doc84", "title": "Payment Verification", "content": "Additional verification may be required for large orders."},
        {"id": "doc85", "title": "Account Integration", "content": "Connect your social media accounts for easier login."},
        {"id": "doc86", "title": "Product Customization", "content": "Some products can be customized - allow extra processing time."},
        {"id": "doc87", "title": "Shipping Times", "content": "Processing time is 1-2 business days before shipment."},
        {"id": "doc88", "title": "Return Methods", "content": "Return items by mail or bring to any retail location."},
        {"id": "doc89", "title": "Payment Options", "content": "We accept all major credit cards and digital wallets."},
        {"id": "doc90", "title": "Account Security Questions", "content": "Set up security questions for additional account protection."},
        {"id": "doc91", "title": "Product Quality", "content": "We stand behind the quality of all our products."},
        {"id": "doc92", "title": "Shipping Updates", "content": "Receive real-time shipping updates via email or text message."},
        {"id": "doc93", "title": "Return Process", "content": "Initiate returns through your account for fastest processing."},
        {"id": "doc94", "title": "Payment Methods Added", "content": "Save multiple payment methods for faster checkout."},
        {"id": "doc95", "title": "Account Profile", "content": "Keep your profile information updated for better service."},
        {"id": "doc96", "title": "Product Support", "content": "Access product support articles and tutorials online."},
        {"id": "doc97", "title": "Shipping International", "content": "International shipping available to most countries worldwide."},
        {"id": "doc98", "title": "Return Policy Extended", "content": "Extended return policy during holiday season."},
        {"id": "doc99", "title": "Payment Security Guarantee", "content": "100% payment security guarantee on all transactions."},
        {"id": "doc100", "title": "Account Family Sharing", "content": "Share account benefits with family members through family plan."}
        ]

            # Convert to LangChain Document objects
        docs = [
            Document(page_content=d["content"], metadata={"title": d["title"], "source_id": d["id"]})
            for d in raw_documents
        ]

        # Add to Weaviate
        vectorstore.add_documents(docs)

        # Run a similarity search
        query = "How long do I have to return an item?"
        results = vectorstore.similarity_search(query, k=2)

        for r in results:
            print("--------------------------------")
            print(r.page_content, r.metadata)

    finally:
        if hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
