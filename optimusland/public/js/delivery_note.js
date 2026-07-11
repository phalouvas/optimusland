frappe.ui.form.on('Delivery Note', {
    refresh: function (frm) {
        // Shipping cost buttons removed — costs are now managed on Draft SI
        // via the additional_costs child table. Historical shipping data
        // on submitted DNs is preserved in the database (fields hidden).
    }
});
                                }
                            });
                        }
                    );
                }).addClass("btn-danger");
            }
        }
    }
});