package com.example.testsampleapp.model;

public class Product {
    private Integer id;
    private String name;
    private String category;
    private Integer unitPrice;
    private Integer weightGram;
    private Boolean taxIncludedFlag;

    public Integer getId() { return id; }
    public void setId(Integer id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }

    public Integer getUnitPrice() { return unitPrice; }
    public void setUnitPrice(Integer unitPrice) { this.unitPrice = unitPrice; }

    public Integer getWeightGram() { return weightGram; }
    public void setWeightGram(Integer weightGram) { this.weightGram = weightGram; }

    public Boolean getTaxIncludedFlag() { return taxIncludedFlag; }
    public void setTaxIncludedFlag(Boolean taxIncludedFlag) { this.taxIncludedFlag = taxIncludedFlag; }
}
