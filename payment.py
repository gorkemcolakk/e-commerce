import time

class PaymentGateway:
    """
    Generic wrapper class for Virtual POS integration.
    You can integrate real POS API services like Iyzico, Stripe, or Param here in the future.
    In its current state, it runs a payment simulation based on credit card rules.
    """
    
    @staticmethod
    def process_payment(amount: float, card_name: str, card_number: str, exp_date: str, cvc: str) -> dict:
        """
        amount: Final order amount (After discounts calculated)
        
        RETURN:
        {"success": True/False, "transaction_id": "...", "message": "Error description"}
        """
        
        # Delay to simulate a real API request (network latency)
        time.sleep(1.2)
        
        # Extract digits only
        clean_number = "".join(filter(str.isdigit, str(card_number)))
        
        # If amount is 0 (Fully paid with gift/discount code), approve directly without going to POS
        if amount == 0:
            return {
                "success": True, 
                "transaction_id": "FREE_" + str(int(time.time() * 1000)),
                "message": "Free transaction successful."
            }

        # TEST CARDS (Simulation Scenarios)
        
        # 1. Always rejected test card:
        if clean_number.startswith('0000'):
            return {"success": False, "message": "Payment rejected: Fake/Test card rule."}
            
        # 2. Insufficient balance/limit test card (Starts with 5111)
        if clean_number.startswith('5111'):
             return {"success": False, "message": "Payment failed: Insufficient card balance or limit."}
             
        # 3. Communication Error
        if clean_number.startswith('9999'):
             return {"success": False, "message": "Could not communicate with the payment system (Timeout)."}

        # GENERAL CONTROLS
        if len(clean_number) < 15 or len(clean_number) > 19:
            return {"success": False, "message": "Invalid card number. (Minimum 15, Maximum 19 Digits)"}
            
        if not exp_date or '/' not in exp_date:
            return {"success": False, "message": "Expiry date is not valid. (Expected: MM/YY)"}
            
        try:
            month, year = exp_date.split('/')
            if int(month) < 1 or int(month) > 12:
                return {"success": False, "message": "Invalid month format. Please enter between 01 and 12."}
        except ValueError:
            return {"success": False, "message": "Invalid expiry date format."}
            
        clean_cvc = "".join(filter(str.isdigit, str(cvc)))
        if len(clean_cvc) < 3 or len(clean_cvc) > 4:
            return {"success": False, "message": "Invalid CVC number."}
            
        # If it didn't hit the conditions above, ACCEPT AS SUCCESSFUL
        transaction_id = "TRX_" + str(int(time.time() * 1000))
        
        return {
            "success": True,
            "transaction_id": transaction_id,
            "message": "Payment Successful"
        }
